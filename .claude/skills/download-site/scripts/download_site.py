#!/usr/bin/env python3
"""
Site Downloader - Download web pages and convert to Markdown

CLI 入口脚本
"""

import argparse
import sys
from pathlib import Path

# 添加模块路径
SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from download_site.downloader import SiteDownloader


def main():
    parser = argparse.ArgumentParser(
        description='下载网页并转换为 Markdown 格式',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  %(prog)s https://example.com/article
  %(prog)s https://docs.python.org/3/ --depth 2
  %(prog)s https://vuejs.org/guide/ --depth 3 --domain-only --output ./vue-docs/
        '''
    )
    parser.add_argument('url', help='要下载的页面地址')
    parser.add_argument('--depth', type=int, default=1,
                        help='递归深度（默认: 1）')
    parser.add_argument('--output', default='./downloaded/',
                        help='输出目录（默认: ./downloaded/）')
    parser.add_argument('--domain-only', action='store_true',
                        help='只下载同域名页面')

    args = parser.parse_args()

    downloader = SiteDownloader(
        base_url=args.url,
        output_dir=args.output,
        max_depth=args.depth,
        domain_only=args.domain_only
    )

    downloaded = downloader.run()

    print(f"\n{'='*50}")
    print("下载完成!")
    print(f"下载页面数: {len(downloaded)}")
    print(f"输出目录: {args.output}")

    if downloaded:
        print("\n已下载文件:")
        for item in downloaded:
            print(f"  - {item['url']} -> {item['file']}")


if __name__ == '__main__':
    main()
