"""导出 PostgreSQL 只读结构契约。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from inkforge_core.db.schema_guard import (
    SchemaConnectionError,
    export_schema_contract,
)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="导出 PostgreSQL 只读数据库结构契约。")
    parser.add_argument("--database-url", required=True, help="PostgreSQL 连接地址。")
    parser.add_argument("--output", required=True, type=Path, help="结构契约输出路径。")
    parser.add_argument("--overwrite", action="store_true", help="显式允许覆盖已有契约。")
    return parser


async def _run(args: argparse.Namespace) -> int:
    try:
        contract = await export_schema_contract(
            args.database_url,
            args.output,
            overwrite=args.overwrite,
        )
    except SchemaConnectionError:
        print("导出失败：无法以只读方式读取数据库结构。", file=sys.stderr)
        return 1
    except FileExistsError:
        print("导出失败：输出文件已存在，请显式使用 --overwrite。", file=sys.stderr)
        return 1

    print(
        "导出成功："
        f"表 {len(contract['tables'])} 张，"
        f"枚举 {len(contract['enums'])} 个，"
        f"来源 {contract['source']['product']} {contract['source']['serverVersion']}，"
        f"指纹 {contract['fingerprint']}"
    )
    return 0


def main() -> int:
    """运行结构契约导出命令。"""

    return asyncio.run(_run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
