"""测试上下文：跨步骤串联接口关联数据。

接口关联的本质是"上一步返回值作为下一步入参"。common 用一个可变的
ScenarioContext 保存每一步产生的动态值（order_id、last_response 等），
后续步骤通过占位符 $key 读取。
"""


class ScenarioContext:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    def set(self, key: str, value: object) -> None:
        self._data[key] = value

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def bind(self, value):
        """把字符串/dict/list 中的 $key 占位符替换为已存的上下文值。"""
        if isinstance(value, str):
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