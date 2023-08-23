import os

from scripts.image import ImageDiagnostic
from scripts.utils.read_files import read_file
import yaml


class TestImageDiagnostic:
    def test_load_from_file(self):
        ImageDiagnostic.parse_obj(yaml.safe_load(open("TEST_config.yml")))

    def test_image_saving(self):
        diagnostic = ImageDiagnostic.parse_obj(yaml.safe_load(open("TEST_config.yml")))

        # set save image location
        diagnostic.save_image_location = os.getcwd()

        result = diagnostic.measure_beamsize(3)

        # read file
        file_info = read_file(result["save_filename"])
        assert file_info["resolution"] == 1.0

        os.remove(result["save_filename"])




