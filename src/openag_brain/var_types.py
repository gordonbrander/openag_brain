from std_msgs.msg import Float64, Int32

from openag.var_types import (
    AIR_TEMPERATURE, AIR_HUMIDITY, AIR_CARBON_DIOXIDE,
    WATER_TEMPERATURE, WATER_POTENTIAL_HYDROGEN, WATER_ELECTRICAL_CONDUCTIVITY,
    WATER_OXIDATION_REDUCTION_POTENTIAL, WATER_DISSOLVED_OXYGEN,
    LIGHT_ILLUMINANCE
)

SENSOR_VARIABLES = (
    (AIR_TEMPERATURE, Float64),
    (AIR_HUMIDITY, Float64),
    (AIR_CARBON_DIOXIDE, Int32),
    (WATER_TEMPERATURE, Float64),
    (WATER_POTENTIAL_HYDROGEN, Float64),
    (WATER_ELECTRICAL_CONDUCTIVITY, Float64),
    (WATER_OXIDATION_REDUCTION_POTENTIAL, Float64),
    (WATER_DISSOLVED_OXYGEN, Float64),
    (LIGHT_ILLUMINANCE, Float64)
)