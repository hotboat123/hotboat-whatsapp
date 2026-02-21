"""
Configuration for availability and booking slots
"""
from typing import List
from dataclasses import dataclass

@dataclass
class ServiceConfig:
    """Configuration for a service type"""
    name: str
    capacity_min: int
    capacity_max: int
    duration_hours: float
    price_per_person: float

@dataclass
class AvailabilityConfig:
    """Configuration for availability checking"""
    operating_hours: List[int]  # List of hours (24h format) when service is available
    duration_hours: float  # Default duration of each booking
    buffer_hours: float  # Buffer time between bookings (default: 0.5 = 30 min)
    exclude_statuses: List[str]  # Statuses to exclude from availability check

# HotBoat specific configuration
# Configuración de paseos cada 3 horas
AVAILABILITY_CONFIG = AvailabilityConfig(
    operating_hours=[8, 11, 14, 17, 20, 23],  # 9am, 12pm, 3pm, 6pm, 9pm (cada 3 horas)
    duration_hours=3.0,  # Each HotBoat trip lasts 2 hours
    buffer_hours=0.0,  # Sin buffer - con 2 HotBoats podemos tener reservas simultáneas
    exclude_statuses=['cancelled', 'rejected']
)

# Service types available
SERVICES = [
    ServiceConfig(
        name="HotBoat Trip 2 people",
        capacity_min=2,
        capacity_max=2,
        duration_hours=2.0,
        price_per_person=69990
    ),
    ServiceConfig(
        name="HotBoat Trip 3 people",
        capacity_min=3,
        capacity_max=3,
        duration_hours=2.0,
        price_per_person=54990
    ),
    ServiceConfig(
        name="HotBoat Trip 4 people",
        capacity_min=4,
        capacity_max=4,
        duration_hours=2.0,
        price_per_person=44990
    ),
    ServiceConfig(
        name="HotBoat Trip 5 people",
        capacity_min=5,
        capacity_max=5,
        duration_hours=2.0,
        price_per_person=38990
    ),
    ServiceConfig(
        name="HotBoat Trip 6 people",
        capacity_min=6,
        capacity_max=6,
        duration_hours=2.0,
        price_per_person=32990
    ),
    ServiceConfig(
        name="HotBoat Trip 7 people",
        capacity_min=7,
        capacity_max=7,
        duration_hours=2.0,
        price_per_person=29990
    ),
]

def get_service_config(service_name: str) -> ServiceConfig:
    """Get service configuration by name"""
    for service in SERVICES:
        if service.name.lower() in service_name.lower():
            return service
    
    # Default service config
    return ServiceConfig(
        name="HotBoat Trip",
        capacity_min=2,
        capacity_max=7,
        duration_hours=2.0,
        price_per_person=0
    )

