"""Domain failures, independent of infrastructure."""


class EngineeringModelError(ValueError):
    """Base class for canonical registry/value validation failures."""


class UnknownEquipmentType(EngineeringModelError):
    pass


class UnknownAttribute(EngineeringModelError):
    pass


class InvalidAttributeValue(EngineeringModelError):
    pass


class InvalidEnumValue(InvalidAttributeValue):
    pass


class UnknownUnit(EngineeringModelError):
    pass


class IncompatibleUnit(EngineeringModelError):
    pass


class InvalidRegistryDefinition(EngineeringModelError):
    pass
