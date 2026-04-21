from .golden_rsi import GoldenRSIStrategy
from .dual_momentum import DualMomentumStrategy
from .week52_high import Week52HighStrategy
from .volatility_breakout import VolatilityBreakoutStrategy
from .bollinger_band import BollingerBandStrategy
from .macd_strategy import MACDStrategy
from .turtle_trading import TurtleTradingStrategy
from .value_investing import ValueInvestingStrategy

STRATEGY_MAP = {
    'golden_rsi': GoldenRSIStrategy,
    'dual_momentum': DualMomentumStrategy,
    'week52_high': Week52HighStrategy,
    'volatility_breakout': VolatilityBreakoutStrategy,
    'bollinger_band': BollingerBandStrategy,
    'macd': MACDStrategy,
    'turtle_trading': TurtleTradingStrategy,
    'value_investing': ValueInvestingStrategy,
}

STRATEGY_LABELS = {
    'golden_rsi': '골든크로스+RSI (국내 안정형)',
    'dual_momentum': '듀얼 모멘텀 (미국 중립형)',
    'week52_high': '52주 신고가 모멘텀 (공격형)',
    'volatility_breakout': '변동성 돌파 (단타형)',
    'bollinger_band': '볼린저 밴드 (변동성 추적형)',
    'macd': 'MACD (추세 추종형)',
    'turtle_trading': '터틀 트레이딩 (추세 추종 시스템)',
    'value_investing': 'PER/PBR 가치투자 (월간 리밸런싱)',
}
