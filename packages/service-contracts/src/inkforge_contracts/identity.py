from typing import Annotated, Literal

from pydantic import StringConstraints

CoreAgentId = Literal["设定", "剧情", "写作", "校验", "编辑"]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
