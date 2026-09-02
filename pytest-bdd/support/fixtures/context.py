"""测试上下文：跨步骤串联接口关联数据。

接口关联的本质是"上一步返回值作为下一步入参"。common 用一个可变的
ScenarioContext 保存每一步产生的动态值（order_id、last_response 等），
后续步骤通过占位符 $key 读取。
"""


import re


class ScenarioContext:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    def set(self, key: str, value: object) -> None:
        self._data[key] = value

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def bind(self, value):
        """把字符串/dict/list 中的 $key 占位符替换为已存的上下文值。

        「整值引用」（整个字符串恰好为 ${xxx}）直接返回上下文**原始对象**：
        save 出的数字/列表/布尔保持原类型，不再 _to_str 转字符串——
        避免 long / array<long> 等 body 字段收到 "5" / ["5"] 字符串，
        导致服务端反序列化出现类型漂移（long 收字符串可能 400 或被强转）。
        """
        if isinstance(value, str):
            m = re.fullmatch(r"\$\{(\w+)\}", value)
            if m and m.group(1) in self._data:
                return self._data[m.group(1)]
            for k, v in self._data.items():
                value = value.replace("${" + k + "}", _to_str(v)).replace("$" + k, _to_str(v))
            return value
        if isinstance(value, dict):
            return {k: self.bind(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.bind(v) for v in value]
        return value


def _to_str(v) -> str:
    return "" if v is None else str(v)