"""S&P 500 및 NASDAQ 100 주요 종목 리스트 (exchange: NAS=NASDAQ, NYS=NYSE)"""

SP500_SYMBOLS = [
    # Technology
    ('AAPL', 'NAS'), ('MSFT', 'NAS'), ('NVDA', 'NAS'), ('AVGO', 'NAS'), ('ORCL', 'NYS'),
    ('CRM', 'NYS'), ('AMD', 'NAS'), ('QCOM', 'NAS'), ('TXN', 'NAS'), ('INTC', 'NAS'),
    ('MU', 'NAS'), ('AMAT', 'NAS'), ('LRCX', 'NAS'), ('KLAC', 'NAS'), ('ADI', 'NAS'),
    ('MRVL', 'NAS'), ('CDNS', 'NAS'), ('SNPS', 'NAS'), ('NXPI', 'NAS'), ('ON', 'NAS'),
    ('MPWR', 'NAS'), ('TER', 'NAS'), ('SWKS', 'NAS'), ('KEYS', 'NYS'), ('ANSS', 'NAS'),
    # Consumer Discretionary
    ('AMZN', 'NAS'), ('TSLA', 'NAS'), ('HD', 'NYS'), ('MCD', 'NYS'), ('NKE', 'NYS'),
    ('SBUX', 'NAS'), ('TGT', 'NYS'), ('LOW', 'NYS'), ('COST', 'NAS'), ('TJX', 'NYS'),
    ('BKNG', 'NAS'), ('ABNB', 'NAS'), ('MAR', 'NAS'), ('GM', 'NYS'), ('F', 'NYS'),
    # Communication Services
    ('GOOGL', 'NAS'), ('GOOG', 'NAS'), ('META', 'NAS'), ('NFLX', 'NAS'), ('DIS', 'NYS'),
    ('CMCSA', 'NAS'), ('T', 'NYS'), ('VZ', 'NYS'), ('TMUS', 'NAS'), ('EA', 'NAS'),
    # Financials
    ('JPM', 'NYS'), ('V', 'NYS'), ('MA', 'NYS'), ('BAC', 'NYS'), ('WFC', 'NYS'),
    ('GS', 'NYS'), ('MS', 'NYS'), ('BLK', 'NYS'), ('SPGI', 'NYS'), ('AXP', 'NYS'),
    ('C', 'NYS'), ('USB', 'NYS'), ('PNC', 'NYS'), ('TFC', 'NYS'), ('COF', 'NYS'),
    # Healthcare
    ('JNJ', 'NYS'), ('LLY', 'NYS'), ('UNH', 'NYS'), ('ABBV', 'NYS'), ('MRK', 'NYS'),
    ('TMO', 'NYS'), ('ABT', 'NYS'), ('ISRG', 'NAS'), ('DHR', 'NYS'), ('BMY', 'NYS'),
    ('AMGN', 'NAS'), ('GILD', 'NAS'), ('REGN', 'NAS'), ('VRTX', 'NAS'), ('BIIB', 'NAS'),
    # Energy
    ('XOM', 'NYS'), ('CVX', 'NYS'), ('COP', 'NYS'), ('SLB', 'NYS'), ('EOG', 'NYS'),
    ('PSX', 'NYS'), ('VLO', 'NYS'), ('MPC', 'NYS'), ('OXY', 'NYS'), ('HAL', 'NYS'),
    # Industrials
    ('CAT', 'NYS'), ('DE', 'NYS'), ('HON', 'NAS'), ('GE', 'NYS'), ('RTX', 'NYS'),
    ('LMT', 'NYS'), ('BA', 'NYS'), ('UPS', 'NYS'), ('FDX', 'NYS'), ('NOC', 'NYS'),
    ('EMR', 'NYS'), ('ETN', 'NYS'), ('PH', 'NYS'), ('ROK', 'NYS'), ('ITW', 'NYS'),
    # Consumer Staples
    ('PG', 'NYS'), ('KO', 'NYS'), ('PEP', 'NAS'), ('WMT', 'NYS'), ('PM', 'NYS'),
    ('MO', 'NYS'), ('CL', 'NYS'), ('KMB', 'NYS'), ('GIS', 'NYS'), ('K', 'NYS'),
    # Materials
    ('LIN', 'NAS'), ('APD', 'NAS'), ('ECL', 'NYS'), ('SHW', 'NYS'), ('NUE', 'NYS'),
    # Real Estate
    ('AMT', 'NYS'), ('PLD', 'NYS'), ('CCI', 'NYS'), ('EQIX', 'NAS'), ('SPG', 'NYS'),
    # Utilities
    ('NEE', 'NYS'), ('DUK', 'NYS'), ('SO', 'NYS'), ('D', 'NYS'), ('AEP', 'NAS'),
    # ETFs
    ('SPY', 'NYS'), ('QQQ', 'NAS'), ('IWM', 'NYS'), ('EFA', 'NYS'), ('GLD', 'NYS'),
]

NASDAQ100_SYMBOLS = [
    ('AAPL', 'NAS'), ('MSFT', 'NAS'), ('NVDA', 'NAS'), ('AMZN', 'NAS'), ('META', 'NAS'),
    ('TSLA', 'NAS'), ('GOOGL', 'NAS'), ('GOOG', 'NAS'), ('AVGO', 'NAS'), ('COST', 'NAS'),
    ('NFLX', 'NAS'), ('AMD', 'NAS'), ('QCOM', 'NAS'), ('TMUS', 'NAS'), ('TXN', 'NAS'),
    ('INTC', 'NAS'), ('INTU', 'NAS'), ('CMCSA', 'NAS'), ('HON', 'NAS'), ('AMGN', 'NAS'),
    ('AMAT', 'NAS'), ('MU', 'NAS'), ('LRCX', 'NAS'), ('MRVL', 'NAS'), ('KLAC', 'NAS'),
    ('PANW', 'NAS'), ('SNPS', 'NAS'), ('CDNS', 'NAS'), ('REGN', 'NAS'), ('ADI', 'NAS'),
    ('CRWD', 'NAS'), ('MELI', 'NAS'), ('FTNT', 'NAS'), ('MDLZ', 'NAS'), ('PYPL', 'NAS'),
    ('GILD', 'NAS'), ('SBUX', 'NAS'), ('CSX', 'NAS'), ('ABNB', 'NAS'), ('ADSK', 'NAS'),
    ('PCAR', 'NAS'), ('NXPI', 'NAS'), ('MAR', 'NAS'), ('MCHP', 'NAS'), ('ORLY', 'NAS'),
    ('MNST', 'NAS'), ('KDP', 'NAS'), ('CTAS', 'NAS'), ('PAYX', 'NAS'), ('AZN', 'NAS'),
    ('VRTX', 'NAS'), ('ISRG', 'NAS'), ('BIIB', 'NAS'), ('IDXX', 'NAS'), ('FAST', 'NAS'),
]

# KOSPI200 주요 종목 (변동성 돌파 스크리너용)
KOSPI200_SYMBOLS = [
    '005930', '000660', '035420', '005380', '000270', '051910', '006400',
    '207940', '005490', '028260', '012330', '066570', '105560', '055550',
    '086790', '003550', '009150', '000810', '010130', '011200', '034730',
    '017670', '030200', '032830', '047050', '033780', '010950', '096770',
    '003490', '000720', '004020', '011790', '021240', '009540', '010140',
    '018260', '011070', '036460', '001570', '139480', '097950', '302440',
    '086280', '271560', '015760', '316140', '006800', '000120', '326030',
]
