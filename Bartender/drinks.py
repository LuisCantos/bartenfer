"""drinks.py — Recetas del Bartender 3.0.

Cada bebida define sus ingredientes en mililitros. pump_controller.py resuelve
qué bomba activar por ingrediente consultando pump_config.json; una bebida
solo puede prepararse si TODOS sus ingredientes tienen bomba asignada.
"""

drink_list = [
    {
        "name": "Gin & Tonic",
        "ingredients": {"gin": 50, "tonica": 150},
    },
    {
        "name": "Cuba Libre",
        "ingredients": {"ron": 50, "cola": 150},
    },
    {
        "name": "Destornillador",
        "ingredients": {"vodka": 50, "naranja": 150},
    },
    {
        "name": "Tequila Sunrise",
        "ingredients": {"tequila": 50, "naranja": 120},
    },
    {
        "name": "Whisky Cola",
        "ingredients": {"whisky": 50, "cola": 150},
    },
]
