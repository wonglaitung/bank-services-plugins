#!/usr/bin/env python3
"""
Site Downloader - 核心下载模块

下载网页及其子页面，转换为 Markdown 格式
"""

import re
from urllib.parse import urljoin, urlparse
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import html2text


class SiteDownloader:
    """网页下载器，支持递归下载和 Markdown 转换"""

    def __init__(self, base_url, output_dir, max_depth, domain_only):
        """
        初始化下载器

        Args:
            base_url: 起始 URL
            output_dir: 输出目录路径
            max_depth: 最大递归深度
            domain_only: 是否只下载同域名页面
        """
        self.base_url = base_url.rstrip('/')
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.domain_only = domain_only
        self.visited = set()
        self.downloaded = []
        self.base_domain = urlparse(base_url).netloc

        # 配置 html2text
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = False
        self.h2t.ignore_emphasis = False
        self.h2t.body_width = 0  # 不换行
        self.h2t.unicode_snob = True
        self.h2t.skip_internal_links = False

    def is_valid_url(self, url):
        """
        检查 URL 是否应该被下载

        Args:
            url: 要检查的 URL

        Returns:
            bool: URL 是否有效
        """
        parsed = urlparse(url)

        # 跳过非 HTTP URL
        if parsed.scheme not in ('http', 'https'):
            return False

        # 跳过仅锚点链接
        if not parsed.path or parsed.path == '/':
            return True

        # 域名检查
        if self.domain_only and parsed.netloc != self.base_domain:
            return False

        # 跳过常见的非内容 URL
        skip_patterns = [
            r'\.(pdf|zip|tar|gz|png|jpg|jpeg|gif|svg|ico|mp4|mp3|avi|mov)$',
            r'/api/',
            r'#',
        ]

        for pattern in skip_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False

        return True

    def url_to_filename(self, url):
        """
        将 URL 转换为有效的文件名

        Args:
            url: 要转换的 URL

        Returns:
            str: 文件名
        """
        parsed = urlparse(url)
        path = parsed.path.strip('/')

        if not path:
            return 'index.md'

        # 清理路径
        path = re.sub(r'[^\w\-/]', '_', path)

        # 移除尾部下划线
        path = path.rstrip('_')

        # 添加 .md 扩展名
        if not path.endswith('.md'):
            path = f"{path}.md"

        return path

    def get_page_links(self, soup, current_url):
        """
        提取页面中的所有链接

        Args:
            soup: BeautifulSoup 对象
            current_url: 当前页面 URL

        Returns:
            set: 链接集合
        """
        links = set()

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']

            # 将相对 URL 转换为绝对 URL
            full_url = urljoin(current_url, href)

            # 移除锚点
            full_url = full_url.split('#')[0]

            if full_url and self.is_valid_url(full_url):
                links.add(full_url)

        return links

    def clean_soup(self, soup):
        """
        移除页面中的噪音元素

        Args:
            soup: BeautifulSoup 对象

        Returns:
            BeautifulSoup: 清理后的对象
        """
        # 移除 script 和 style 元素
        for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()

        # 移除常见的噪音元素（按 class）
        for class_name in ['sidebar', 'nav', 'navigation', 'menu', 'footer',
                           'header', 'ads', 'advertisement']:
            for element in soup.find_all(class_=class_name):
                element.decompose()

        # 移除特定 ID 的元素
        for id_name in ['sidebar', 'nav', 'navigation', 'menu', 'footer', 'header']:
            element = soup.find(id=id_name)
            if element:
                element.decompose()

        return soup

    def download_page(self, url, depth=0):
        """
        下载单个页面及其子页面

        Args:
            url: 要下载的 URL
            depth: 当前递归深度
        """
        if url in self.visited or depth > self.max_depth:
            return

        self.visited.add(url)

        try:
            print(f"正在下载: {url}")
            response = requests.get(url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; SiteDownloader/1.0)'
            })
            response.raise_for_status()

            # 解析 HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # 在清理前获取链接
            links = self.get_page_links(soup, url) if depth < self.max_depth else set()

            # 清理内容
            soup = self.clean_soup(soup)

            # 查找主要内容区域
            main_content = (
                soup.find('main') or
                soup.find('article') or
                soup.find('div', class_=re.compile(r'content|main|article', re.I)) or
                soup.find('body') or
                soup
            )

            # 转换为 Markdown
            markdown = self.h2t.handle(str(main_content))

            # 保存文件
            filename = self.url_to_filename(url)
            filepath = self.output_dir / filename

            # 创建子目录
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # 添加源 URL 作为头部
            content = f"<!-- Source: {url} -->\n\n# {urlparse(url).path.strip('/') or 'Index'}\n\n{markdown}"

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            self.downloaded.append({
                'url': url,
                'file': str(filepath)
            })

            print(f"  已保存: {filepath}")

            # 下载子页面
            for link in links:
                self.download_page(link, depth + 1)

        except requests.RequestException as e:
            print(f"  下载错误 {url}: {e}")
        except Exception as e:
            print(f"  处理错误 {url}: {e}")

    def run(self):
        """
        启动下载过程

        Returns:
            list: 已下载的文件列表
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_page(self.base_url)

        return self.downloaded
