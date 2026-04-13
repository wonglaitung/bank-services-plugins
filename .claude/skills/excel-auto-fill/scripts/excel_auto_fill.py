#!/usr/bin/env python3
"""
Excel 模版自动填充工具
支持多种标记格式和匹配策略

用法：
    python excel_auto_fill.py template.xlsx '{"name": "John", "amount": 1000}'
    python excel_auto_fill.py template.xlsx data.json -o output.xlsx
    python excel_auto_fill.py template.xlsx -d "name: John\\namount: 1000"
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

# 添加技能目录到路径，从技能内部导入模块
# 路径: scripts -> excel-auto-fill (技能根目录)
SCRIPT_DIR = Path(__file__).parent.parent  # skills/excel-auto-fill/
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from excel_auto_fill.skill import excel_auto_fill, FillResult
    from excel_auto_fill.path_utils import normalize_path, normalize_output_path
except ImportError:
    print("错误：无法导入 excel_auto_fill 模块")
    print("请确保 excel_auto_fill 目录在技能目录下")
    sys.exit(1)


def setup_logging(verbose: bool = False) -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger('excel_auto_fill_cli')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # 清除已有处理器
    logger.handlers.clear()
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger


def parse_data_input(data_str: str) -> Union[str, Dict[str, Any]]:
    """
    解析数据输入
    
    支持格式：
    - JSON 文件路径（支持跨平台格式：~、\\、/ 等）
    - JSON 字符串
    - 键值对文本（name: value）
    """
    # 检查是否为文件路径
    data_path = Path(data_str)
    if data_path.exists():
        # Normalize path for cross-platform compatibility
        normalized_path = normalize_path(data_str)
        with open(normalized_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 根据文件扩展名解析
        if data_path.suffix.lower() == '.json':
            return json.loads(content)
        else:
            return content.strip()
    
    # 尝试解析为 JSON
    try:
        return json.loads(data_str)
    except json.JSONDecodeError:
        # 不是 JSON，当作键值对文本
        return data_str


def print_result(result: FillResult, verbose: bool = False) -> None:
    """打印操作结果"""
    if result.success:
        print("\n" + "=" * 50)
        print("填充成功!")
        print("=" * 50)
        print(f"输出文件: {result.output_path}")
        
        if result.stats:
            print(f"\n统计信息:")
            print(f"  - 已填充字段: {result.stats.get('fields_filled', 0)}")
            print(f"  - 已填充单元格: {result.stats.get('cells_filled', 0)}")
            print(f"  - 匹配字段: {result.stats.get('matched_fields', 0)}")
        
        if verbose and result.mapping_result:
            print(f"\n映射详情:")
            print(f"  - 匹配的输入字段: {result.mapping_result.matched_input_fields}")
            print(f"  - 未匹配的输入字段: {result.mapping_result.unmatched_input_fields}")
    else:
        print("\n" + "=" * 50)
        print("填充失败!")
        print("=" * 50)
        for error in result.errors:
            print(f"  错误: {error}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Excel 模版自动填充工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用 JSON 字符串填充
  python excel_auto_fill.py template.xlsx '{"name": "John", "amount": 1000}'
  
  # 使用 JSON 文件填充
  python excel_auto_fill.py template.xlsx data.json
  
  # 指定输出文件
  python excel_auto_fill.py template.xlsx data.json -o output.xlsx
  
  # 使用键值对文本
  python excel_auto_fill.py template.xlsx -d "name: John\\namount: 1000"
  
  # 使用自定义映射
  python excel_auto_fill.py template.xlsx data.json -m mapping.yaml
  
  # 覆盖已存在的输出文件
  python excel_auto_fill.py template.xlsx data.json --overwrite

更多信息请参考 SKILL.md
        """
    )
    
    parser.add_argument('template', help='Excel 模版文件路径 (.xlsx, .xls, .xlsm)')
    parser.add_argument('data', nargs='?', help='数据（JSON 字符串或文件路径）')
    parser.add_argument('-d', '--data-text', help='键值对格式的数据文本')
    parser.add_argument('-o', '--output', help='输出文件路径（默认: template_filled.xlsx）')
    parser.add_argument('-m', '--mapping', help='自定义映射配置文件（YAML/JSON）')
    parser.add_argument('-t', '--threshold', type=int, default=70,
                        help='模糊匹配阈值 0-100（默认: 70）')
    parser.add_argument('-l', '--label-column', type=int,
                        help='字段名所在列号（1-based），用于垂直布局模版。例如: 2 表示字段名在 B 列')
    parser.add_argument('--no-preview', action='store_true',
                        help='跳过映射预览')
    parser.add_argument('--default', default='',
                        help='缺失字段的默认值')
    parser.add_argument('--overwrite', action='store_true',
                        help='覆盖已存在的输出文件')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='显示详细信息')
    parser.add_argument('--help-zh', action='store_true',
                        help='显示中文帮助')
    
    args = parser.parse_args()
    
    # 显示中文帮助
    if args.help_zh:
        parser.print_help()
        return
    
    # 验证必要参数
    if not args.data and not args.data_text:
        parser.error('请提供数据参数（data 或 --data-text）')
    
    # 设置日志
    logger = setup_logging(args.verbose)
    
    # 规范化模板路径（跨平台兼容）
    normalized_template = normalize_path(args.template)
    logger.info(f"模板路径: {normalized_template}")
    
    # 规范化输出路径（如果指定）
    normalized_output = None
    if args.output:
        normalized_output = normalize_output_path(args.output)
        logger.info(f"输出路径: {normalized_output}")
    
    # 规范化映射配置路径（如果指定）
    normalized_mapping = None
    if args.mapping:
        normalized_mapping = normalize_path(args.mapping)
        logger.info(f"映射配置路径: {normalized_mapping}")
    
    # 解析数据输入
    try:
        if args.data_text:
            data_input = args.data_text
        else:
            data_input = parse_data_input(args.data)
        
        logger.info(f"数据解析完成")
    except Exception as e:
        logger.error(f"数据解析失败: {e}")
        sys.exit(1)
    
    # 执行填充
    logger.info(f"开始处理模版: {normalized_template}")
    
    result = excel_auto_fill(
        template=normalized_template,
        data=data_input,
        output=normalized_output,
        mapping=normalized_mapping,
        threshold=args.threshold,
        preview=not args.no_preview,
        default_value=args.default,
        overwrite=args.overwrite,
        label_column=args.label_column
    )
    
    # 打印结果
    print_result(result, args.verbose)
    
    # 返回退出码
    sys.exit(0 if result.success else 1)


if __name__ == '__main__':
    main()
