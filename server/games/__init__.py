from .familiada import Familiada
from .floor import Floor
from .melody import Melody
from .millionaires import Millionaires
from .one_of_ten import OneOfTen
from .tournament import Tournament

GAMES = {cls.id: cls for cls in (OneOfTen, Melody, Floor, Familiada, Millionaires, Tournament)}
