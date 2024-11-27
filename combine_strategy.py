import asyncio
import datetime
import os
from dotenv import load_dotenv
import random
from pprint import pprint
import tinkoff

from tinkoff.invest import AsyncClient
from tinkoff.invest.async_services import AsyncServices
from tinkoff.invest.schemas import Quotation, Share, Etf

from filters import (
    is_rsi_more_than,
    is_sma_growing,
    get_instr,
)

from utils import (
    get_quotation,
    get_price,
    change_quotation,
)

load_dotenv()

TOKEN = os.getenv('COMBINE_STRATEGY')
account_combine_strategy = 'Combine_Strategy'
MAX_PRICE_ONE_POSITION = 500
VOLUME_FOR_STOPS = 2  # %


async def buyer(
        client: AsyncServices,
        instrument: tuple[Share | Etf, float],
        account,
        last_prices,
):
    # pprint(instrument)
    portfolio_live = await client.operations.get_portfolio(account_id=account.id)
    free_money = portfolio_live.total_amount_currencies.units + portfolio_live.total_amount_currencies.nano / 10 ** 9

    lots_quantity = None
    last_price = None
    cost_one_lot = None
    for last_price in last_prices.last_prices:
        if last_price.instrument_uid == instrument[0].uid:
            # Price of instrument
            cost_one_lot = (last_price.price.units + last_price.price.nano / 10 ** 9) * instrument[0].lot

            # If cost of  one lot  more then i have money in  account
            if free_money - cost_one_lot <= 10:
                print(f'Не хватает бабла на счёте {instrument[0].ticker} price: {last_price.price}')
                print(f'*min_price_inc {instrument[0].min_price_increment}')
                return
            lots_quantity = int(MAX_PRICE_ONE_POSITION / cost_one_lot)
            break
    if not lots_quantity:
        return

    for positions in portfolio_live.positions:
        if instrument[0].uid == positions.instrument_uid:
            print(f'{instrument[0].ticker} уже  есть')
            return

    try:
        purchase = await client.orders.post_order(
            quantity=lots_quantity,
            direction=1,
            account_id=account.id,
            order_type=2,
            order_id=f"{random.randint(0, 0xFFFFFFFF):08X}",
            instrument_id=instrument[0].uid,
            price=Quotation(units=last_price.price.units, nano=last_price.price.nano)
        )
        print(f'*purchase: {purchase}')
        price_take_profit_q = change_quotation(
            last_price.price,
            instrument[0].min_price_increment,
            VOLUME_FOR_STOPS,
            increase=True)
        print('*cost_one_lot:', cost_one_lot)
        print(f'*price_take_profit_q: {price_take_profit_q}')

        is_take_profit = False
        while not is_take_profit:
            try:
                take_profit = await  client.stop_orders.post_stop_order(
                    quantity=lots_quantity,
                    direction=2,
                    account_id=account.id,
                    instrument_id=instrument[0].uid,
                    exchange_order_type=1,
                    stop_price=price_take_profit_q,
                    price_type=2,
                    expiration_type=1,
                    stop_order_type=1,
                )
                print('*take_profit', take_profit)
                is_take_profit = True
            finally:
                pass

        price_stop_loss_q = change_quotation(
            last_price.price,
            instrument[0].min_price_increment,
            VOLUME_FOR_STOPS,
            increase=False,
        )

        is_stop_loss = False
        while not is_stop_loss:
            try:
                stop_loss = await  client.stop_orders.post_stop_order(
                    quantity=lots_quantity,
                    direction=2,
                    account_id=account.id,
                    instrument_id=instrument[0].uid,
                    exchange_order_type=1,
                    stop_price=price_stop_loss_q,
                    price_type=2,
                    expiration_type=1,
                    stop_order_type=2,
                )
                print('*stop_loss', stop_loss)
                is_stop_loss = True
            finally:
                pass

    except tinkoff.invest.exceptions.AioRequestError as e:
        print(f'Error!: {e}')


async def trader():
    async with AsyncClient(TOKEN) as client:
        # getting brokers account
        accounts = await  client.users.get_accounts()
        for account in accounts.accounts:
            if account.name == account_combine_strategy:
                break

        # getting portfolio from account
        portfolio = await client.operations.get_portfolio(account_id=account.id)

        # getting positions in portfolio
        bought_instr_uid = []  # купленные инструменты
        rub = None
        for instr_in_port in portfolio.positions:
            if instr_in_port.instrument_uid == 'a92e2e25-a698-45cc-a781-167cf465257c':
                rub = instr_in_port

            else:
                bought_instr_uid.append(instr_in_port.instrument_uid)

        if rub.quantity.units < MAX_PRICE_ONE_POSITION:
            print(
                f'Денег на счету ({rub.quantity.units}) менее чем разрешено для торговли в базе данных ({MAX_PRICE_ONE_POSITION})')
            return

        instrs = await get_instr(client)
        coro = [is_sma_growing(client, instr, semaphore=asyncio.Semaphore(15)) for instr in instrs]
        instrs = [instr for instr in await asyncio.gather(*coro) if instr]
        coro = [is_rsi_more_than(client, instr, semaphore=asyncio.Semaphore(15)) for instr in instrs]
        instrs = sorted([instr for instr in await asyncio.gather(*coro) if instr],
                        key=lambda instr: instr[1])

        last_prices = await client.market_data.get_last_prices(instrument_id=[instr[0].uid for instr in instrs])
        # print('*last_prices', last_prices)
        print(f'{datetime.datetime.now()}:  {len(instrs)}')
        for instr in instrs:
            if instr[0].uid not in bought_instr_uid:
                await buyer(client, instr, account, last_prices)


async def main():
    exec_time = None
    while True:
        if exec_time is None or datetime.datetime.now() - exec_time >= datetime.timedelta(minutes=1):
            exec_time = datetime.datetime.now()
            await trader()
        else:
            await asyncio.sleep(10)


if __name__ == '__main__':
    asyncio.run(main())
