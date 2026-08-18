from dataclasses import asdict, dataclass


@dataclass
class HallazgoIntegridad:
    codigo: str
    severidad: str  # error | advertencia
    modulo: str
    entidad: str
    registro: str
    descripcion: str
    recomendacion: str

    def a_dict(self):
        return asdict(self)
