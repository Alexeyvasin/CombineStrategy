import os
from dotenv import load_dotenv
import asyncio
from datetime import datetime, timedelta
from pprint import pprint

from tinkoff.invest import AsyncClient
from tinkoff.invest.utils import now
from tinkoff.invest import Share, Etf
from tinkoff.invest.async_services import AsyncServices
from tinkoff.invest.schemas import (
    GetTechAnalysisRequest,
    IndicatorType,
    IndicatorInterval,
    TypeOfPrice,
    Deviation,
    Smoothing,
    InstrumentStatus,
    InstrumentExchangeType,
    SecurityTradingStatus,
)

from utils import get_quotation, get_price

load_dotenv()

TOKEN = os.getenv('RSI_30')

sem_for_sma_growing = asyncio.Semaphore(1)


# def get_request(
#         indicator_type: IndicatorType,
#         instrument_uid: str,
#         from_: datetime,
#         to: datetime,
#         interval: IndicatorInterval,
#         type_of_price: TypeOfPrice,
#         length: int,
#         deviation: Deviation,
#         smoothing: Smoothing
# ) -> GetTechAnalysisRequest:
#     return GetTechAnalysisRequest(
#         indicator_type=indicator_type,
#         instrument_uid=instrument_uid,
#         from_=from_,
#         to=to,
#         interval=interval,
#         type_of_price=type_of_price,
#         length=length,
#         deviation=deviation,
#         smoothing=smoothing,
#     )

async def is_sma_growing(
        client: AsyncServices,
        instrument: Share | Etf,
        from_=None,
        to=None,
        interval=IndicatorInterval.INDICATOR_INTERVAL_ONE_HOUR,
        type_of_price=TypeOfPrice.TYPE_OF_PRICE_CLOSE,
        length=9,
        semaphore=None,
) -> Share | Etf | None:
    semaphore = sem_for_sma_growing if semaphore is None else semaphore
    to = now() if to is None else to
    from_ = to - timedelta(days=3) if from_ is None else from_
    async with semaphore:
        res = await client.market_data.get_tech_analysis(
            request=GetTechAnalysisRequest(
                indicator_type=IndicatorType.INDICATOR_TYPE_SMA,
                instrument_uid=instrument.uid,
                from_=from_,
                to=to,
                interval=interval,
                type_of_price=type_of_price,
                length=length,
            )
        )
    if len(res.technical_indicators) < 2:
        return None
    last_price = res.technical_indicators[-1].signal.units + res.technical_indicators[-1].signal.nano / 10 ** 9
    before_last_price = res.technical_indicators[-2].signal.units + res.technical_indicators[-2].signal.nano / 10 ** 9
    # pprint(res.technical_indicators[-1:-3: -1])
    # pprint(res.technical_indicators[-2])

    if last_price > before_last_price:
        # print('*grow', instrument.ticker, last_price, before_last_price)
        return instrument


sem_for_rsi_more_than = asyncio.Semaphore(1)


async def is_rsi_more_than(
        client: AsyncServices,
        instrument: Share | Etf,
        threshold=35,
        from_=None,
        to=None,
        interval=None,
        type_of_price=None,
        length=None,
        semaphore=None,
) -> tuple[Share | Etf, float] | None:
    length = 14 if length is None else length
    type_of_price = TypeOfPrice.TYPE_OF_PRICE_CLOSE \
        if type_of_price is None else type_of_price
    interval = IndicatorInterval.INDICATOR_INTERVAL_ONE_HOUR \
        if interval is None else interval
    to = now() if to is None else to
    from_ = to - timedelta(days=3) if from_ is None else from_
    async with semaphore:
        res = await client.market_data.get_tech_analysis(
            request=GetTechAnalysisRequest(
                indicator_type=IndicatorType.INDICATOR_TYPE_RSI,
                instrument_uid=instrument.uid,
                from_=from_,
                to=to,
                interval=interval,
                type_of_price=type_of_price,
                length=length,
            )
        )
    last_rsi = res.technical_indicators[-1].signal
    # pprint(res.technical_indicators)
    rsi_price = get_price(last_rsi)
    if rsi_price < threshold:
        # print('*rsi', instrument.ticker, last_rsi)
        return instrument, rsi_price


async def get_instr(
        client: AsyncServices,
        shares: bool = True,
        etfs: bool = True,
        instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE,
        trading_status: list = None,
) -> tuple:
    trading_statuses = [
        SecurityTradingStatus.SECURITY_TRADING_STATUS_NORMAL_TRADING] \
        if trading_status is None else trading_status

    coro = []
    instruments = []
    coro.append(client.instruments.shares(
        instrument_status=instrument_status,
    )) if shares else None
    coro.append(client.instruments.etfs(
        instrument_status=instrument_status,
    )) if etfs else None

    set_or_instrs = await asyncio.gather(*coro)
    for instrs in set_or_instrs:
        for instr in instrs.instruments:
            if (instr.trading_status in trading_statuses and
                not instr.for_qual_investor_flag and
                    instr.exchange != 'unknown' and
                    instr.api_trade_available_flag
            ):
                instruments.append(instr)
    return instruments


async def main():
    async with (AsyncClient(TOKEN) as client):
        shares = await client.instruments.shares(
            instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE,
            # instrument_exchange=InstrumentExchangeType.INSTRUMENT_EXCHANGE_DEALER,
        )

        shares = [share for share in shares.instruments
                  if (share.trading_status == SecurityTradingStatus.SECURITY_TRADING_STATUS_NORMAL_TRADING or
                      # share.trading_status == SecurityTradingStatus.SECURITY_TRADING_STATUS_DEALER_NORMAL_TRADING or
                      share.trading_status == SecurityTradingStatus.SECURITY_TRADING_STATUS_NOT_AVAILABLE_FOR_TRADING) and
                  share.exchange != 'unknown' and
                  share.api_trade_available_flag and
                  not share.for_qual_investor_flag
                  ]

        coro = (is_sma_growing(client, share, semaphore=asyncio.Semaphore(15)) for share in shares)
        instrs_growing_sma = (res for res in await asyncio.gather(*coro) if res)

        coro = (is_rsi_more_than(client, instr, semaphore=asyncio.Semaphore(15)) for instr in instrs_growing_sma)
        instr_rsi_more_than = sorted([instr for instr in await asyncio.gather(*coro) if instr],
                                     key=lambda instr: instr[1])
        pprint(instr_rsi_more_than)

        # await get_instr(client)


if __name__ == '__main__':
    asyncio.run(main())
