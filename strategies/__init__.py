from .golden_rsi import GoldenRSIStrategy
from .dual_momentum import DualMomentumStrategy
from .week52_high import Week52HighStrategy
from .volatility_breakout import VolatilityBreakoutStrategy

STRATEGY_MAP = {
    'golden_rsi': GoldenRSIStrategy,
    'dual_momentum': DualMomentumStrategy,
    'week52_high': Week52HighStrategy,
    'volatility_breakout': VolatilityBreakoutStrategy,
}

STRATEGY_LABELS = {
    'golden_rsi': '골든크로스+RSI (국내 안정형)',
    'dual_momentum': '듀얼 모멘텀 (미국 중립형)',
    'week52_high': '52주 신고가 모멘텀 (공격형)',
    'volatility_breakout': '변동성 돌파 (단타형)',
}
