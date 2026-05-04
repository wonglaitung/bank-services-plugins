#!/usr/bin/env python3
"""
Site Downloader 测试模块
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from urllib.parse import urlparse

# 添加模块路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from download_site.downloader import SiteDownloader


class TestSiteDownloader:
    """SiteDownloader 测试类"""

    @pytest.fixture
    def downloader(self):
        """创建测试用的下载器实例"""
        return SiteDownloader(
            base_url='https://example.com',
            output_dir='./test_output/',
            max_depth=1,
            domain_only=False
        )

    def test_init(self, downloader):
        """测试初始化"""
        assert downloader.base_url == 'https://example.com'
        assert downloader.max_depth == 1
        assert downloader.domain_only is False
        assert downloader.base_domain == 'example.com'
        assert len(downloader.visited) == 0
        assert len(downloader.downloaded) == 0

    def test_is_valid_url_http(self, downloader):
        """测试 HTTP URL 验证"""
        assert downloader.is_valid_url('https://example.com/page') is True
        assert downloader.is_valid_url('http://example.com/page') is True

    def test_is_valid_url_non_http(self, downloader):
        """测试非 HTTP URL 应被跳过"""
        assert downloader.is_valid_url('ftp://example.com/file') is False
        assert downloader.is_valid_url('mailto:test@example.com') is False
        assert downloader.is_valid_url('javascript:void(0)') is False

    def test_is_valid_url_skip_patterns(self, downloader):
        """测试应跳过的 URL 模式"""
        assert downloader.is_valid_url('https://example.com/file.pdf') is False
        assert downloader.is_valid_url('https://example.com/file.png') is False
        assert downloader.is_valid_url('https://example.com/api/data') is False

    def test_is_valid_url_domain_only(self):
        """测试域名限制模式"""
        downloader = SiteDownloader(
            base_url='https://example.com',
            output_dir='./test_output/',
            max_depth=1,
            domain_only=True
        )

        assert downloader.is_valid_url('https://example.com/page') is True
        assert downloader.is_valid_url('https://other.com/page') is False

    def test_url_to_filename(self, downloader):
        """测试 URL 转文件名"""
        assert downloader.url_to_filename('https://example.com/') == 'index.md'
        assert downloader.url_to_filename('https://example.com/article') == 'article.md'
        assert downloader.url_to_filename('https://example.com/docs/guide') == 'docs/guide.md'

    def test_url_to_filename_special_chars(self, downloader):
        """测试特殊字符处理"""
        filename = downloader.url_to_filename('https://example.com/article with spaces')
        assert ' ' not in filename
        assert filename.endswith('.md')

    def test_clean_soup_removes_scripts(self, downloader):
        """测试清理脚本元素"""
        from bs4 import BeautifulSoup

        html = '''
        <html>
            <head><script>var x = 1;</script></head>
            <body>
                <nav>Navigation</nav>
                <p>Content</p>
                <footer>Footer</footer>
            </body>
        </html>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        cleaned = downloader.clean_soup(soup)

        assert cleaned.find('script') is None
        assert cleaned.find('nav') is None
        assert cleaned.find('footer') is None
        assert cleaned.find('p') is not None

    def test_get_page_links(self, downloader):
        """测试提取页面链接"""
        from bs4 import BeautifulSoup

        html = '''
        <html>
            <body>
                <a href="/page1">Page 1</a>
                <a href="https://example.com/page2">Page 2</a>
                <a href="https://other.com/page3">Page 3</a>
                <a href="#anchor">Anchor</a>
            </body>
        </html>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        links = downloader.get_page_links(soup, 'https://example.com/')

        assert 'https://example.com/page1' in links
        assert 'https://example.com/page2' in links
        # 锚点链接应被移除
        for link in links:
            assert '#' not in link

    def test_get_page_links_domain_only(self):
        """测试域名限制下的链接提取"""
        from bs4 import BeautifulSoup

        downloader = SiteDownloader(
            base_url='https://example.com',
            output_dir='./test_output/',
            max_depth=1,
            domain_only=True
        )

        html = '''
        <html>
            <body>
                <a href="/page1">Page 1</a>
                <a href="https://other.com/page2">Page 2</a>
            </body>
        </html>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        links = downloader.get_page_links(soup, 'https://example.com/')

        assert 'https://example.com/page1' in links
        assert 'https://other.com/page2' not in links

    @patch('download_site.downloader.requests.get')
    def test_download_page_success(self, mock_get, downloader, tmp_path):
        """测试成功下载页面"""
        # 设置模拟响应
        mock_response = Mock()
        mock_response.text = '''
        <html>
            <body>
                <article>
                    <h1>Test Article</h1>
                    <p>This is test content.</p>
                </article>
            </body>
        </html>
        '''
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # 更新输出目录为临时路径
        downloader.output_dir = tmp_path

        # 执行下载
        downloader.download_page('https://example.com/test')

        # 验证
        assert len(downloader.downloaded) == 1
        assert downloader.downloaded[0]['url'] == 'https://example.com/test'

        # 验证文件已创建
        output_file = Path(downloader.downloaded[0]['file'])
        assert output_file.exists()

        # 验证文件内容
        content = output_file.read_text(encoding='utf-8')
        assert '<!-- Source: https://example.com/test -->' in content

    @patch('download_site.downloader.requests.get')
    def test_download_page_error(self, mock_get, downloader, tmp_path):
        """测试下载错误处理"""
        import requests

        # 模拟网络错误
        mock_get.side_effect = requests.RequestException('Network error')

        downloader.output_dir = tmp_path
        downloader.download_page('https://example.com/error')

        # 应该没有下载成功
        assert len(downloader.downloaded) == 0

    def test_run_creates_output_dir(self, tmp_path):
        """测试自动创建输出目录"""
        output_dir = tmp_path / 'new_dir' / 'subdir'

        with patch.object(SiteDownloader, 'download_page'):
            downloader = SiteDownloader(
                base_url='https://example.com',
                output_dir=str(output_dir),
                max_depth=0,
                domain_only=False
            )
            downloader.run()

        assert output_dir.exists()


class TestUrlHandling:
    """URL 处理测试"""

    def test_url_with_query_params(self):
        """测试带查询参数的 URL"""
        downloader = SiteDownloader(
            base_url='https://example.com',
            output_dir='./test/',
            max_depth=1,
            domain_only=False
        )

        filename = downloader.url_to_filename('https://example.com/page?id=123')
        assert filename.endswith('.md')

    def test_url_with_trailing_slash(self):
        """测试尾部斜杠处理"""
        downloader = SiteDownloader(
            base_url='https://example.com/',
            output_dir='./test/',
            max_depth=1,
            domain_only=False
        )

        assert downloader.base_url == 'https://example.com'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
