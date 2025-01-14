import json
import logging
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import numpy.typing as npt

from ...control.config_manager import config
from ...definitions.types import Color3f, LabelingMode
from ...utils.color import hex_to_rgb, rgb_to_hex
from ...utils.singleton import SingletonABCMeta
from .exceptions import (
    DefaultIdMismatchException,
    LabelClassNameEmpty,
    LabelIdsNotUniqueException,
    ZeroLabelException,
)


@dataclass
class ClassConfig:
    name: str
    id: int
    color: Color3f

    @classmethod
    def from_dict(cls, data: dict) -> "ClassConfig":
        return cls(name=data["name"], id=data["id"], color=hex_to_rgb(data["color"]))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "id": self.id,
            "color": rgb_to_hex(self.color),
        }


class LabelConfig(object, metaclass=SingletonABCMeta):
    def __init__(self) -> None:
        self.classes: List[ClassConfig]
        self.default: int
        self.type: LabelingMode
        self.format: str

        if getattr(self, "_loaded", False) != True:
            self.load_config()

    def load_config(self) -> None:
        class_definition_path = config.getpath("FILE", "class_definitions")
        if class_definition_path.exists():
            with config.getpath("FILE", "class_definitions").open("r") as stream:
                data = json.load(stream)

            self.classes = [ClassConfig.from_dict(c) for c in data["classes"]]
            self.default = data["default"]
            self.type = LabelingMode(data["type"])
            self.format = data["format"]
        else:
            self.classes = [ClassConfig("cart", 0, color=Color3f(1, 0, 0))]
            self.default = 0
            self.type = LabelingMode.OBJECT_DETECTION
            self.format = ".bin"
        self.validate()
        self._loaded = True

    def save_config(self) -> None:
        self.validate()
        data = {
            "classes": [c.to_dict() for c in self.classes],
            "default": self.default,
            "type": self.type.value,
            "format": self.format,
        }
        with config.getpath("FILE", "class_definitions").open("w") as stream:
            json.dump(data, stream, indent=4)

    @property
    def nb_of_classes(self) -> int:
        return len(self.classes)

    @property
    def color_map(self) -> npt.NDArray[np.float32]:
        """An (N, 3) array where N is the number of classes and color_map[i] represents the i-th class' rgb color."""
        return np.array([c.color[0:3] for c in self.classes]).astype(np.float32)

    @property
    def class_order(self) -> npt.NDArray[np.int8]:
        """An array lookup table to look up the order of a class id in the label definition."""
        max_class_id = max(c.id for c in self.classes) + 1
        lookup = -np.ones((max_class_id,), dtype=np.int8)
        for order, c in enumerate(self.classes):
            lookup[c.id] = order
        return lookup

    # GETTERS

    def get_classes(self) -> Dict[str, ClassConfig]:
        return {c.name: c for c in self.classes}

    def get_class(self, class_name: str) -> ClassConfig:
        return self.get_classes()[class_name]

    def get_class_color(self, class_name: str) -> Color3f:
        try:
            return self.get_classes()[class_name].color
        except KeyError:
            logging.warning(
                f"No color defined for class '{class_name}'!" "Proceeding with red."
            )
            return hex_to_rgb("#FF0000")

    def has_valid_default_class(self) -> bool:
        for c in self.classes:
            if c.id == self.default:
                return True
        return False

    def get_default_class_name(self) -> str:
        for c in self.classes:
            if c.id == self.default:
                return c.name
        raise DefaultIdMismatchException(
            f"Default class id `{self.default}` is missing in the class list."
        )

    # SETTERS

    def set_default_class(self, class_name: str) -> None:
        self.default = next((c.id for c in self.classes if c.name == class_name))
        self.save_config()

    def set_class_color(self, class_name: str, color: Color3f) -> None:
        self.get_class(class_name).color = color
        self.save_config()

    def set_first_as_default(self) -> None:
        self.default = self.classes[0].id

    # VALIDATION
    def validate(self) -> None:
        if self.nb_of_classes == 0:
            raise ZeroLabelException("At least one label required.")
        # validate the default id presents in the classes
        self.get_default_class_name()
        # validate the ids are unique
        if len({c.id for c in self.classes}) != self.nb_of_classes:
            raise LabelIdsNotUniqueException("Class ids are not unique.")

        for label_class in self.classes:
            if label_class.name == "":
                raise LabelClassNameEmpty("At least one class name is empty.")
