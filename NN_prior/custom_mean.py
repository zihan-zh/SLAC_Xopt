import torch
from gpytorch.means.mean import Mean
from gpytorch.priors import NormalPrior, GammaPrior
from gpytorch.constraints import Positive
from transformed_model import TransformedModel


class CustomMean(TransformedModel, Mean):
    def __init__(
            self,
            model: torch.nn.Module,
            gp_input_transform: torch.nn.Module,
            gp_outcome_transform: torch.nn.Module,
    ):
        """Custom prior mean for a GP based on an arbitrary model.

        Args:
            model: Representation of the model.
            gp_input_transform: Module used to transform inputs in the GP.
            gp_outcome_transform: Module used to transform outcomes in the GP.
        """
        super(CustomMean, self).__init__(model, gp_input_transform,
                                         gp_outcome_transform)

    def evaluate_model(self, x):
        """Placeholder method which can be used to modify model calls."""
        return self.model(x)

    def forward(self, x):
        # set transformers to eval mode
        self.input_transformer.eval()
        self.outcome_transformer.eval()
        # transform inputs to mean space
        x_model = self.input_transformer.untransform(x)
        # evaluate model
        y_model = self.evaluate_model(x_model)
        # transform outputs
        y = self.outcome_transformer(y_model)[0]
        self.input_transformer.eval()
        self.outcome_transformer.eval()
        return y


class LinearInputCalibration(CustomMean):
    def __init__(
            self,
            model: torch.nn.Module,
            gp_input_transform: torch.nn.Module,
            gp_outcome_transform: torch.nn.Module,
            **kwargs,
    ):
        """Prior mean with learnable linear input calibration.

        Inputs are passed through decoupled linear calibration nodes
        with learnable shift and scaling parameters:
        y = model(x_scale * (x + x_shift)).

        Args:
            model: Inherited from CustomMean.
            gp_input_transform: Inherited from CustomMean.
            gp_outcome_transform: Inherited from CustomMean.

        Keyword Args:
            x_dim (int): The input dimension. Defaults to 1.
            x_shift_prior (gpytorch.priors.Prior): Prior over x_shift.
              Defaults to a Normal distribution.
            x_scale_constraint (torch.nn.Module): Parameter constraint for
              x_scale. Defaults to positive.
            x_scale_prior (gpytorch.priors.Prior): Prior over x_scale.
              Defaults to a Gamma distribution (concentration=2.0, rate=2.0).

        Attributes:
            x_shift (torch.nn.Parameter): Parameter tensor of size x_dim.
            x_scale (torch.nn.Parameter): Parameter tensor of size x_dim.
        """
        super().__init__(model, gp_input_transform, gp_outcome_transform)
        self.x_dim = kwargs.get("x_dim", 1)
        self.x_shift = torch.nn.Parameter(torch.randn(self.x_dim))
        x_shift_prior = kwargs.get(
            "x_shift_prior",
            NormalPrior(loc=torch.zeros((1, self.x_dim)),
                        scale=torch.ones((1, self.x_dim)))
        )
        self.register_prior("x_shift_prior", x_shift_prior, "x_shift")
        self.raw_x_scale = torch.nn.Parameter(torch.randn(self.x_dim))
        x_scale_constraint = kwargs.get("x_scale_constraint",
                                        Positive())
        self.register_constraint("raw_x_scale", x_scale_constraint)
        x_scale_prior = kwargs.get(
            "x_scale_prior",
            GammaPrior(concentration=2.0 * torch.ones((1, self.x_dim)),
                       rate=2.0 * torch.ones((1, self.x_dim)))
        )
        self.register_prior("x_scale_prior", x_scale_prior, "x_scale")

    @property
    def x_scale(self):
        x_scale = self.raw_x_scale_constraint.transform(self.raw_x_scale)
        return x_scale

    @x_scale.setter
    def x_scale(self, value):
        return self._set_x_scale(value)

    def _set_x_scale(self, value):
        if not torch.is_tensor(value):
            value = torch.as_tensor(value).to(self.raw_x_scale)
        self.initialize(
            raw_x_scale=self.raw_x_scale_constraint.inverse_transform(value))

    def input_calibration(self, x):
        return self.x_scale * (x + self.x_shift)

    def evaluate_model(self, x):
        return self.model(self.input_calibration(x))


class LinearOutputCalibration(CustomMean):
    def __init__(
            self,
            model: torch.nn.Module,
            gp_input_transform: torch.nn.Module,
            gp_outcome_transform: torch.nn.Module,
            **kwargs,
    ):
        """Prior mean with learnable linear output calibration.

        Outputs are passed through decoupled linear calibration nodes
        with learnable shift and scaling parameters:
        y = y_scale * (model(x) + y_shift).

        Args:
            model: Inherited from CustomMean.
            gp_input_transform: Inherited from CustomMean.
            gp_outcome_transform: Inherited from CustomMean.

        Keyword Args:
            y_dim (int): The output dimension. Defaults to 1.
            y_shift_prior (gpytorch.priors.Prior): Prior over y_shift.
              Defaults to a Normal distribution.
            y_scale_constraint (torch.nn.Module): Parameter constraint for
              y_scale. Defaults to positive.
            y_scale_prior (gpytorch.priors.Prior): Prior over y_scale.
              Defaults to a Gamma distribution (concentration=2.0, rate=2.0).

        Attributes:
            y_shift (torch.nn.Parameter): Parameter tensor of size y_dim.
            y_scale (torch.nn.Parameter): Parameter tensor of size y_dim.
        """
        super().__init__(model, gp_input_transform, gp_outcome_transform)
        self.y_dim = kwargs.get("y_dim", 1)
        self.y_shift = torch.nn.Parameter(torch.randn(self.y_dim))
        y_shift_prior = kwargs.get(
            "y_shift_prior",
            NormalPrior(loc=torch.zeros((1, self.y_dim)),
                        scale=torch.ones((1, self.y_dim)))
        )
        self.register_prior("y_shift_prior", y_shift_prior, "y_shift")
        self.raw_y_scale = torch.nn.Parameter(torch.randn(self.y_dim))
        y_scale_constraint = kwargs.get("y_scale_constraint",
                                        Positive())
        self.register_constraint("raw_y_scale", y_scale_constraint)
        y_scale_prior = kwargs.get(
            "y_scale_prior",
            GammaPrior(concentration=2.0 * torch.ones((1, self.y_dim)),
                       rate=2.0 * torch.ones((1, self.y_dim)))
        )
        self.register_prior("y_scale_prior", y_scale_prior, "y_scale")

    @property
    def y_scale(self):
        y_scale = self.raw_y_scale_constraint.transform(self.raw_y_scale)
        return y_scale

    @y_scale.setter
    def y_scale(self, value):
        return self._set_y_scale(value)

    def _set_y_scale(self, value):
        if not torch.is_tensor(value):
            value = torch.as_tensor(value).to(self.raw_y_scale)
        self.initialize(
            raw_y_scale=self.raw_y_scale_constraint.inverse_transform(value))

    def output_calibration(self, y):
        return self.y_scale * (y + self.y_shift)

    def evaluate_model(self, x):
        return self.output_calibration(self.model(x))


class LinearCalibration(LinearInputCalibration, LinearOutputCalibration):
    def __init__(
            self,
            model: torch.nn.Module,
            gp_input_transform: torch.nn.Module,
            gp_outcome_transform: torch.nn.Module,
            **kwargs,
    ):
        """Prior mean with learnable linear input and output calibrations.

        Inputs and outputs are passed through decoupled linear calibration
        nodes with learnable shift and scaling parameters:
        y = y_scale * model(x_scale * (x + x_shift)) + y_shift.

        Args:
            model: Inherited from CustomMean.
            gp_input_transform: Inherited from CustomMean.
            gp_outcome_transform: Inherited from CustomMean.
        """
        super().__init__(model, gp_input_transform, gp_outcome_transform,
                         **kwargs)

    def evaluate_model(self, x):
        return self.output_calibration(self.model(self.input_calibration(x)))


class OutputOffsetCalibration(CustomMean):
    def __init__(
            self,
            model: torch.nn.Module,
            gp_input_transform: torch.nn.Module,
            gp_outcome_transform: torch.nn.Module,
            **kwargs,
    ):
        """Prior mean with learnable output offset calibration.

        Outputs are augmented by a learnable offset parameter:
        y = model(x) + y_shift.

        Args:
            model: Inherited from CustomMean.
            gp_input_transform: Inherited from CustomMean.
            gp_outcome_transform: Inherited from CustomMean.

        Keyword Args:
            y_dim (int): The output dimension. Defaults to 1.
            y_shift_prior (gpytorch.priors.Prior): Prior over y_shift.
              Defaults to None.
            y_shift_constraint (torch.nn.Module): Parameter constraint for
              y_shift. Defaults to None.

        Attributes:
            y_shift (torch.nn.Parameter): Parameter tensor of size y_dim.
        """
        super().__init__(model, gp_input_transform, gp_outcome_transform)
        self.y_dim = kwargs.get("y_dim", 1)
        self.register_parameter("raw_y_shift",
                                torch.nn.Parameter(torch.zeros(self.y_dim)))
        y_shift_prior = kwargs.get("y_shift_prior")
        if y_shift_prior is not None:
            self.register_prior("y_shift_prior", y_shift_prior,
                                self._y_shift_param, self._y_shift_closure)
        y_shift_constraint = kwargs.get("y_shift_constraint")
        if y_shift_constraint is not None:
            self.register_constraint("raw_y_shift", y_shift_constraint)

    @property
    def y_shift(self):
        return self._y_shift_param(self)

    @y_shift.setter
    def y_shift(self, value):
        self._y_shift_closure(self, value)

    def _y_shift_param(self, m):
        if hasattr(m, "raw_y_shift_constraint"):
            return m.raw_y_shift_constraint.transform(m.raw_y_shift)
        return m.raw_y_shift

    def _y_shift_closure(self, m, value):
        if not torch.is_tensor(value):
            value = torch.as_tensor(value).to(m.raw_y_shift)
        if hasattr(m, "raw_y_shift_constraint"):
            m.initialize(
                raw_y_shift=m.raw_y_shift_constraint.inverse_transform(value))
        else:
            m.initialize(raw_y_shift=value)

    def output_calibration(self, y):
        return y + self.y_shift

    def evaluate_model(self, x):
        return self.output_calibration(self.model(x))


class OutputScaleCalibration(CustomMean):
    def __init__(
            self,
            model: torch.nn.Module,
            gp_input_transform: torch.nn.Module,
            gp_outcome_transform: torch.nn.Module,
            **kwargs,
    ):
        """Prior mean with learnable output scale calibration.

        Outputs are augmented by a learnable scaling parameter:
        y = y_scale * model(x).

        Args:
            model: Inherited from CustomMean.
            gp_input_transform: Inherited from CustomMean.
            gp_outcome_transform: Inherited from CustomMean.

        Keyword Args:
            y_dim (int): The output dimension. Defaults to 1.
            y_scale_prior (gpytorch.priors.Prior): Prior over y_scale.
              Defaults to None.
            y_scale_constraint (torch.nn.Module): Parameter constraint for
              y_scale. Defaults to None.

        Attributes:
            y_scale (torch.nn.Parameter): Parameter tensor of size y_dim.
        """
        super().__init__(model, gp_input_transform, gp_outcome_transform)
        self.y_dim = kwargs.get("y_dim", 1)
        self.register_parameter("raw_y_scale",
                                torch.nn.Parameter(torch.zeros(self.y_dim)))
        y_scale_prior = kwargs.get("y_scale_prior")
        if y_scale_prior is not None:
            self.register_prior("y_scale_prior", y_scale_prior,
                                self._y_scale_param, self._y_scale_closure)
        y_scale_constraint = kwargs.get("y_scale_constraint")
        if y_scale_constraint is not None:
            self.register_constraint("raw_y_scale", y_scale_constraint)

    @property
    def y_scale(self):
        return self._y_scale_param(self)

    @y_scale.setter
    def y_scale(self, value):
        self._y_scale_closure(self, value)

    def _y_scale_param(self, m):
        if hasattr(m, "raw_y_scale_constraint"):
            return m.raw_y_scale_constraint.transform(m.raw_y_scale)
        return m.raw_y_scale

    def _y_scale_closure(self, m, value):
        if not torch.is_tensor(value):
            value = torch.as_tensor(value).to(m.raw_y_scale)
        if hasattr(m, "raw_y_scale_constraint"):
            m.initialize(
                raw_y_scale=m.raw_y_scale_constraint.inverse_transform(value))
        else:
            m.initialize(raw_y_scale=value)

    def output_calibration(self, y):
        return self.y_scale * y

    def evaluate_model(self, x):
        return self.output_calibration(self.model(x))


class OutputOffset(CustomMean):
    def __init__(
            self,
            model: torch.nn.Module,
            gp_input_transform: torch.nn.Module,
            gp_outcome_transform: torch.nn.Module,
            y_shift: float,
    ):
        """Prior mean with a constant output offset.

        Args:
            model: Inherited from CustomMean.
            gp_input_transform: Inherited from CustomMean.
            gp_outcome_transform: Inherited from CustomMean.
            y_shift: Value of the constant output offset.
        """
        super().__init__(model, gp_input_transform, gp_outcome_transform)
        self.y_shift = y_shift

    def evaluate_model(self, x):
        return self.model(x) + self.y_shift


class Flatten(CustomMean):
    def __init__(
            self,
            model: torch.nn.Module,
            gp_input_transform: torch.nn.Module,
            gp_outcome_transform: torch.nn.Module,
            **kwargs,
    ):
        """Prior mean composed of a weighted sum with a constant prior.

        The output is a time/step-dependent, weighted sum of the prior mean
        derived from the given model and a constant prior:
        y = (1 - w) * model(x) + w * const.

        Args:
            model: Inherited from CustomMean.
            gp_input_transform: Inherited from CustomMean.
            gp_outcome_transform: Inherited from CustomMean.

        Keyword Args:
            step_range (tuple): Step range over which weighting parameter w
              is changed from minimum to maximum value. Defaults to (0, 10).
            w_lim (tuple): Minimum and maximum value of weighting parameter w.
              Defaults to (0.01, 0.99).

        Attributes:
            constant (torch.nn.Parameter): Parameter tensor of size y_dim.
        """
        super().__init__(model, gp_input_transform, gp_outcome_transform)
        self.step = 0
        self.y_dim = kwargs.get("y_dim", 1)
        self.step_range = kwargs.get("step_range", (0, 10))
        self.w_lim = kwargs.get("w_lim", (0.01, 0.99))
        self.register_parameter("constant",
                                torch.nn.Parameter(torch.zeros(self.y_dim)))
        constant_prior = kwargs.get("constant_prior")
        if constant_prior is not None:
            self.register_prior("constant_prior", constant_prior,
                                self._constant_param, self._constant_closure)
        constant_constraint = kwargs.get("constant_constraint")
        if constant_constraint is not None:
            self.register_constraint("raw_constant", constant_constraint)

    @property
    def constant(self):
        return self._constant_param(self)

    @constant.setter
    def constant(self, value):
        self._constant_closure(self, value)

    def _constant_param(self, m):
        if hasattr(m, "raw_constant_constraint"):
            return m.raw_constant_constraint.transform(m.raw_constant)
        return m.raw_constant

    def _constant_closure(self, m, value):
        if not torch.is_tensor(value):
            value = torch.as_tensor(value).to(m.raw_constant)
        if hasattr(m, "raw_constant_constraint"):
            m.initialize(
                raw_constant=m.raw_constant_constraint.inverse_transform(value))
        else:
            m.initialize(raw_constant=value)

    def evaluate_model(self, x):
        step_delta = self.step_range[1] - self.step_range[0]
        m = (self.w_lim[1] - self.w_lim[0]) / step_delta
        if self.step < self.step_range[0]:
            w = self.w_lim[0]
        else:
            w = self.w_lim[0] + m * (self.step - self.step_range[0])
        w = torch.clip(torch.tensor(w), min=self.w_lim[0], max=self.w_lim[1])
        return (1 - w) * self.model(x) + w * self.constant
