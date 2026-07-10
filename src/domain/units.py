# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Pure unit conversion functions — no external dependencies."""


def kg_to_lbs(kg: float) -> float:
    """Convert kilograms to pounds."""
    return round(kg * 2.20462, 2)


def lbs_to_kg(lbs: float) -> float:
    """Convert pounds to kilograms."""
    return round(lbs / 2.20462, 2)


def cm_to_inches(cm: float) -> float:
    """Convert centimetres to inches."""
    return round(cm / 2.54, 2)


def inches_to_cm(inches: float) -> float:
    """Convert inches to centimetres."""
    return round(inches * 2.54, 2)


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return round(c * 9 / 5 + 32, 2)


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return round((f - 32) * 5 / 9, 2)
