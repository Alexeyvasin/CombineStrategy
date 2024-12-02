from tinkoff.invest.schemas import Quotation


def get_price(q: Quotation) -> float:
    return q.units + q.nano / 10 ** 9


def get_quotation(price: float) -> Quotation:
    units = int(price)
    nano = int((price - units) * 10 ** 9)
    return Quotation(units=units, nano=nano)


def change_quotation(price_q: Quotation, min_inc_q: Quotation, changing_percents: float,
                     increase: bool = True) -> Quotation:
    target_price_q: Quotation = price_q
    price = get_price(price_q)
    if increase:
        target_price = price + price * changing_percents / 100
        while get_price(target_price_q) < target_price:
            target_price_q.units += min_inc_q.units
            target_price_q.nano += min_inc_q.nano
            if target_price_q.nano >= 10 ** 9:
                target_price_q.units += target_price_q.nano // (10 ** 9)
                target_price_q.nano = target_price_q.nano % (10 ** 9)
        return target_price_q
    else:
        target_price = price - price * changing_percents / 100
        while target_price < get_price(target_price_q):
            target_price_q.units -= min_inc_q.units
            target_price_q.nano -= min_inc_q.nano
            if target_price_q.nano < 0:
                target_price_q.units -= 1
                target_price_q.nano = (10 ** 9) - target_price_q.nano
        return target_price_q


def main():
    res = change_quotation(
        Quotation(units=10, nano=860000000),
        Quotation(units=0, nano=10000000),
        2,
        increase=False,
    )
    print(res)


if __name__ == '__main__':
    main()