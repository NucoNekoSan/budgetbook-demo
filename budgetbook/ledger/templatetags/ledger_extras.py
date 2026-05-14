from django import template

register = template.Library()


@register.filter
def yen(value):
    if value in (None, ''):
        return '¥0'
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return value
    return f'¥{amount:,}'


@register.filter
def sub(a, b):
    """テンプレ用減算: {{ a|sub:b }}"""
    try:
        return int(a) - int(b)
    except (TypeError, ValueError):
        return 0


@register.filter
def div(a, b):
    """テンプレ用除算（小数点付き）: {{ 1500|div:100 }} → 15.0"""
    try:
        b = float(b)
        if b == 0:
            return 0
        result = float(a) / b
        # 整数表示できるならそうする
        if result == int(result):
            return int(result)
        return round(result, 2)
    except (TypeError, ValueError):
        return 0


@register.filter
def get_item(d, key):
    """dict のキーアクセス: {{ d|get_item:'foo' }}"""
    if d is None:
        return None
    try:
        return d.get(key)
    except AttributeError:
        try:
            return d[key]
        except (KeyError, TypeError):
            return None