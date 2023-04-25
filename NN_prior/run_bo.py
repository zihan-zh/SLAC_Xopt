import os
import sys
import time
import torch
import warnings
import utilities as util

from botorch.models.transforms.input import Normalize
from botorch.models.transforms.outcome import Standardize
from custom_mean import CustomMean, OutputOffsetCalibration, \
    OutputScaleCalibration, OutputOffset, Flatten
from optimizer import BayesOpt


warnings.filterwarnings('ignore')

# run configuration
idx_config = int(sys.argv[1])
n_epoch = int(sys.argv[2])
configs = ["constant_prior", "no_adjustment", "offset_calibration",
           "scale_calibration", "fixed_offset", "flatten", "alternate"]
config = configs[idx_config]
acq_name = "EI"  # "EI" or "UCB"
n_init = 3  # number of initial samples
n_run = 100  # number of runs
n_step = 50  # number of steps for BO

# output directory
output_path = os.path.dirname(__file__) + "/BO/{}/{}/".format(config, acq_name)
if not os.path.exists(output_path):
    os.makedirs(output_path)

# define device
if torch.cuda.is_available():
    dev = 'cuda:0'
else:
    dev = 'cpu'

# load surrogate model
surrogate = util.Surrogate()
Objective = util.NegativeTransverseBeamSize
ground_truth = Objective(surrogate.model.to(dev))

# definition of custom mean function
input_transformer = Normalize(surrogate.x_dim, bounds=surrogate.x_lim.T)
outcome_transformer = Standardize(1)
custom_mean = None
if not config == "constant_prior":
    corr_model = util.load_correlated_model(n_epoch, surrogate)[0].to(dev)
    params = [Objective(corr_model), input_transformer, outcome_transformer]
    if config == "no_adjustment" or config == "alternate":
        custom_mean = CustomMean(*params)
    elif config == "offset_calibration":
        custom_mean = OutputOffsetCalibration(*params)
    elif config == "scale_calibration":
        custom_mean = OutputScaleCalibration(*params)
    elif config == "fixed_offset":
        custom_mean = OutputOffset(*params, y_shift=5e-3)
    elif config == "flatten":
        custom_mean = Flatten(*params, step_range=(5, 15), w_lim=(0.01, 0.99))

# store data
x = torch.empty((n_run, n_init + n_step, surrogate.x_dim)).to(dev)
y = torch.empty((n_run, n_init + n_step, 1)).to(dev)

# store learnable parameters of custom mean
p_names = []
if custom_mean is not None:
    for name, param in custom_mean.named_parameters():
        if param.requires_grad:
            if name.startswith("raw_"):
                p_names.append(name[4:])
            else:
                p_names.append(name)
p = torch.empty((len(p_names), n_run, n_step)).to(dev)

# MAE and correlation
n_samples = 10000
cutoff_value = None
x_eval = surrogate.sample_x(n_samples, seed=0).to(dev)
y_eval = ground_truth(x_eval).detach()
mae_const = torch.zeros((n_run, n_step))
mae_post = torch.zeros((n_run, n_step))
corr_post = torch.zeros((n_run, n_step))

# BO loop
print("Started BO Loop...")
t0 = time.time()
for run_idx in range(n_run):
    bo = BayesOpt(surrogate, ground_truth, n_init=n_init, n_step=n_step)
    bo.initialize()
    for i in range(n_step):
        if config == "flatten":
            custom_mean.step = i
        if config == "alternate" and i % 4 == 0:
            bo.step(None, acq_name=acq_name, fixed_feature=True, verbose=0)
        else:
            bo.step(custom_mean, acq_name=acq_name, fixed_feature=True,
                    verbose=0)
        if config == "constant_prior":
            y_const = bo.gp.mean_module.constant * torch.ones_like(y_eval)
            mae_const[run_idx, i] = util.calc_mean_absolute_error(
                y_eval, y_const.to(dev))
        post_mean = bo.gp.posterior(x_eval).mean.to(dev)
        mae_post[run_idx, i] = util.calc_mean_absolute_error(y_eval, post_mean)
        corr_post[run_idx, i] = util.calc_correlation(y_eval, post_mean)
        if p_names:
            for idx_param, name in enumerate(p_names):
                p[idx_param] = getattr(custom_mean, name).detach()
    x[run_idx], y[run_idx] = bo.x, bo.y
t_total = time.time() - t0
t_r = t_total / 60  # in minutes
if t_r <= 1.0:
    t_info = "{:.2f} sec".format(60 * t_r)
else:
    t_info = "{:.2f} min".format(t_r)
print("Total runtime: {}".format(t_info))

# save data to file
data = {"x": x, "y": y, "mae_post": mae_post, "corr_post": corr_post}
if p_names:
    for idx_param, name in enumerate(p_names):
        data[name] = p[idx_param]
if config == "constant_prior":
    file_name = "constant.pt"
    data["mae_const"] = torch.tensor(mae_const)
else:
    file_name = "ep={:d}.pt".format(n_epoch)
torch.save(data, output_path + file_name)
