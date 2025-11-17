import json
import os
import re
from typing import List, Dict, Tuple, Any, Optional


class TextProcessor():
    # 定义日语字符集的正则表达式
    JAPANESE_CHAR_SET_CONTENT = (
        r'\u3040-\u309F'
        r'\u30A0-\u30FF'
        r'\u30FB-\u30FE'
        r'\uFF65-\uFF9F'
        r'\u4E00-\u9FFF'
        r'\u3400-\u4DBF'
        r'\u3001-\u303F'
        r'\uff01-\uff5e'
    )

    # 正则库路径
    DEFAULT_REGEX_DIR = os.path.join(".", "Resource", "Regex", "regex.json")

    # 数字序号与空白内容正则
    RE_DIGITAL_SEQ_PRE_STR = r'^(\d+)\.'
    RE_DIGITAL_SEQ_REC_STR = r'^【(\d+)】'
    RE_WHITESPACE_AFFIX_STR = r'^(\s*)(.*?)(\s*)$'

    # 新增：标签处理正则表达式
    # 带冒号的单标签
    RE_SINGLE_TAG_PATTERN_STR = r'^(<[^:>]+:)(.*?)(>)$'
    # 所有标签格式
    RE_MULTI_TAG_PATTERN_STR = r'(<[^>]+>)'

    # 新增：区分两种标签类型的正则
    # <name:content>
    RE_COLON_TAG_PATTERN_STR = r'^(<[^:>]+:)(.*?)(>)$'
    # <name>
    RE_SIMPLE_TAG_PATTERN_STR = r'^(<[^:>]+>)$'

    def __init__(self, config: Any):
        super().__init__()

        current_regex_dir = self.DEFAULT_REGEX_DIR

        # 预编译固定处理的正则表达式
        self.RE_DIGITAL_SEQ_PRE = re.compile(self.RE_DIGITAL_SEQ_PRE_STR)
        self.RE_DIGITAL_SEQ_REC = re.compile(self.RE_DIGITAL_SEQ_REC_STR)

        # 多行处理正则（使用MULTILINE标志）
        self.RE_WHITESPACE_AFFIX = re.compile(self.RE_WHITESPACE_AFFIX_STR, re.MULTILINE)

        # 新增：预编译标签处理正则
        self.RE_SINGLE_TAG_PATTERN = re.compile(self.RE_SINGLE_TAG_PATTERN_STR, re.DOTALL)
        self.RE_MULTI_TAG_PATTERN = re.compile(self.RE_MULTI_TAG_PATTERN_STR, re.DOTALL)

        # 新增：预编译新的标签类型正则
        self.RE_COLON_TAG_PATTERN = re.compile(self.RE_COLON_TAG_PATTERN_STR, re.DOTALL)
        self.RE_SIMPLE_TAG_PATTERN = re.compile(self.RE_SIMPLE_TAG_PATTERN_STR, re.DOTALL)

        # 日语字符处理正则
        ja_affix_pattern_str = (
            rf'(^[^{self.JAPANESE_CHAR_SET_CONTENT}]*)'  # Group 1: Prefix
            rf'(.*?)'  # Group 2: Core text
            rf'([^{self.JAPANESE_CHAR_SET_CONTENT}]*$)'  # Group 3: Suffix
        )
        self.RE_JA_AFFIX = re.compile(ja_affix_pattern_str, re.MULTILINE)

        # 预编译文本前后替换正则
        self.pre_translation_rules_compiled = self._compile_translation_rules(
            config.pre_translation_data
        )
        self.post_translation_rules_compiled = self._compile_translation_rules(
            config.post_translation_data
        )

        # 预编译自动处理正则
        code_pattern_strings = self._prepare_code_pattern_strings(
            config.exclusion_list_data, current_regex_dir
        )

        special_placeholder_pattern_strings = self._build_dynamic_pattern_strings(
            code_pattern_strings, r"\s*{p}\s*"
        )
        self.auto_compiled_patterns = [
            re.compile(p_str, re.IGNORECASE | re.MULTILINE)
            for p_str in special_placeholder_pattern_strings if p_str
        ]

    # ==================== 新增：标签处理相关方法 ====================

    def _is_single_tag_only(self, text: str) -> bool:
        """检查文本是否只包含一个标签（支持注释处理）"""
        # 如果传入的text还没有去注释，先去注释
        if '//' in text or '#' in text or '/*' in text:
            text = self._remove_comments(text)

        text_stripped = text.strip()

        # 必须以 < 开头，> 结尾
        if not (text_stripped.startswith('<') and text_stripped.endswith('>')):
            return False

        # 查找所有标签（包括有冒号和无冒号的）
        matches = list(self.RE_MULTI_TAG_PATTERN.finditer(text_stripped))

        # 只有一个标签，且这个标签覆盖整个文本
        if len(matches) == 1:
            match = matches[0]
            return match.start() == 0 and match.end() == len(text_stripped)

        return False

    def _process_single_tag_content(self, text: str) -> Tuple[str, Optional[Dict]]:
        """处理单个标签（支持注释处理）"""
        # 先移除注释
        text_without_comments = self._remove_comments(text)

        if not self._is_single_tag_only(text_without_comments):
            return text, None

        text_stripped = text_without_comments.strip()

        # 判断标签类型
        colon_match = self.RE_COLON_TAG_PATTERN.match(text_stripped)
        simple_match = self.RE_SIMPLE_TAG_PATTERN.match(text_stripped)

        if colon_match:
            # 带冒号的标签处理
            tag_prefix = colon_match.group(1)
            tag_content = colon_match.group(2)
            tag_suffix = colon_match.group(3)

            # 处理空白（基于去注释后的文本）
            leading_ws = text_without_comments[:len(text_without_comments) - len(text_without_comments.lstrip())]
            trailing_ws = text_without_comments[len(text_without_comments.rstrip()):]
            content_leading_ws = tag_content[:len(tag_content) - len(tag_content.lstrip())]
            content_trailing_ws = tag_content[len(tag_content.rstrip()):]
            core_content = tag_content.strip()

            tag_info = {
                'type': 'single_tag',
                'tag_type': 'colon_tag',
                'tag_prefix': tag_prefix,
                'tag_suffix': tag_suffix,
                'leading_whitespace': leading_ws,
                'trailing_whitespace': trailing_ws,
                'content_leading_whitespace': content_leading_ws,
                'content_trailing_whitespace': content_trailing_ws,
                'comments_removed': True
            }
            return core_content, tag_info

        elif simple_match:
            # 简单标签处理
            full_tag = simple_match.group(1)

            # 处理空白
            leading_ws = text_without_comments[:len(text_without_comments) - len(text_without_comments.lstrip())]
            trailing_ws = text_without_comments[len(text_without_comments.rstrip()):]

            tag_info = {
                'type': 'single_tag',
                'tag_type': 'simple_tag',
                'full_tag': full_tag,
                'leading_whitespace': leading_ws,
                'trailing_whitespace': trailing_ws,
                'content_leading_whitespace': '',
                'content_trailing_whitespace': '',
                'comments_removed': True
            }
            return '', tag_info  # 简单标签返回空内容

        return text, None

    def _remove_comments(self, text: str) -> str:
        """
        移除文本中的注释
        支持格式: // 注释, # 注释, /* 注释 */
        """
        # 按行处理，移除行注释
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            # 移除 // 注释
            if '//' in line:
                line = line.split('//')[0]

            # 移除 # 注释（但要避免误删代码中的 # 符号）
            # if '#' in line and not line.strip().startswith('#'):
            #     # 简单检查：如果 # 前有空白，可能是注释
            #     parts = line.split('#')
            #     if len(parts) > 1 and parts[0].rstrip() != parts[0]:  # # 前有空白
            #         line = parts[0]

            cleaned_lines.append(line)

        result = '\n'.join(cleaned_lines)

        # 移除 /* */ 块注释
        import re
        result = re.sub(r'/\*.*?\*/', '', result, flags=re.DOTALL)

        return result

    def _process_multiple_tags_only(self, text: str) -> Tuple[str, Optional[Dict]]:
        """处理仅包含多个标签的文本"""
        # 先移除注释
        text_without_comments = self._remove_comments(text)

        matches = list(self.RE_MULTI_TAG_PATTERN.finditer(text_without_comments))

        if len(matches) < 2:  # 少于2个标签，不处理
            return text, None

        # 检查是否整个文本只包含这些标签
        reconstructed = ""
        last_end = 0

        for i, match in enumerate(matches):
            # 添加标签前的内容
            before_tag = text_without_comments[last_end:match.start()]
            reconstructed += before_tag

            # 添加标签
            reconstructed += match.group(0)
            last_end = match.end()

        # 添加最后一个标签后的内容
        after_last_tag = text_without_comments[last_end:]
        reconstructed += after_last_tag

        # 检查重建的内容是否与原文一致
        if reconstructed != text_without_comments:
            return text, None

        # 检查标签外是否只有空白字符
        content_between_tags = ""
        last_end = 0
        for match in matches:
            content_between_tags += text_without_comments[last_end:match.start()]
            last_end = match.end()
        content_between_tags += text_without_comments[last_end:]

        # 如果标签外有非空白内容，跳过处理
        if content_between_tags.strip():
            return text, None

        # 提取标签信息时区分两种类型
        tag_infos = []
        extracted_contents = []
        separators = []
        last_end = 0

        for i, match in enumerate(matches):
            # 记录标签前的分隔符
            separator = text_without_comments[last_end:match.start()]
            if i == 0:
                # 第一个标签前的内容作为前缀
                separators.append(separator)
            else:
                # 标签间的分隔符
                separators.append(separator)

            # 完整的标签内容
            full_tag = match.group(0)

            # 判断标签类型
            colon_match = self.RE_COLON_TAG_PATTERN.match(full_tag)
            simple_match = self.RE_SIMPLE_TAG_PATTERN.match(full_tag)

            if colon_match:
                # 带冒号的标签
                tag_prefix = colon_match.group(1)
                tag_content = colon_match.group(2)
                tag_suffix = colon_match.group(3)

                content_leading_ws = tag_content[:len(tag_content) - len(tag_content.lstrip())]
                content_trailing_ws = tag_content[len(tag_content.rstrip()):]
                core_content = tag_content.strip()

                tag_info = {
                    'index': i,
                    'tag_type': 'colon_tag',
                    'tag_prefix': tag_prefix,
                    'tag_suffix': tag_suffix,
                    'content_leading_whitespace': content_leading_ws,
                    'content_trailing_whitespace': content_trailing_ws
                }
                extracted_contents.append(core_content)

            elif simple_match:
                # 简单标签
                tag_info = {
                    'index': i,
                    'tag_type': 'simple_tag',
                    'full_tag': full_tag,
                    'content_leading_whitespace': '',
                    'content_trailing_whitespace': ''
                }
                extracted_contents.append('')  # 简单标签添加空字符串

            else:
                continue

            tag_infos.append(tag_info)
            last_end = match.end()

        # 记录最后一个标签后的内容作为后缀
        final_separator = text_without_comments[last_end:]
        separators.append(final_separator)

        # 合并内容用于翻译
        combined_content = '\n===TAG_SEPARATOR===\n'.join(extracted_contents)

        multi_tag_info = {
            'type': 'multiple_tags',
            'tag_infos': tag_infos,
            'separators': separators,
            'tag_count': len(tag_infos),
            # 标记已移除注释
            'comments_removed': True
        }

        return combined_content, multi_tag_info

    def _process_tag_content(self, text: str) -> Tuple[str, Optional[Dict]]:
        """统一标签处理入口"""
        # 先尝试多标签（避免被单标签贪婪匹配）
        multi_result, multi_info = self._process_multiple_tags_only(text)
        if multi_info:
            return multi_result, multi_info

        # 再尝试单标签
        single_result, single_info = self._process_single_tag_content(text)
        if single_info:
            return single_result, single_info

        return text, None

    def _restore_single_tag_content(self, content: str, tag_info: Dict) -> str:
        """还原单标签"""
        tag_type = tag_info.get('tag_type', 'colon_tag')

        if tag_type == 'colon_tag':
            return (
                    tag_info['leading_whitespace'] +
                    tag_info['tag_prefix'] +
                    tag_info['content_leading_whitespace'] +
                    content +
                    tag_info['content_trailing_whitespace'] +
                    tag_info['tag_suffix'] +
                    tag_info['trailing_whitespace']
            )
        elif tag_type == 'simple_tag':
            return (
                    tag_info['leading_whitespace'] +
                    tag_info['full_tag'] +
                    tag_info['trailing_whitespace']
            )

        return content

    def _restore_multiple_tags(self, translated_content: str, multi_tag_info: Dict) -> str:
        """还原多标签"""
        tag_infos = multi_tag_info['tag_infos']
        separators = multi_tag_info['separators']
        expected_count = multi_tag_info['tag_count']

        # 分割翻译结果
        translated_parts = translated_content.split('\n===TAG_SEPARATOR===\n')

        if len(translated_parts) != expected_count:
            print(f"[Warning]: 多标签分割数量不匹配! 期望{expected_count}个，实际{len(translated_parts)}个")
            while len(translated_parts) < expected_count:
                translated_parts.append('')
            translated_parts = translated_parts[:expected_count]

        # 重建整个文本
        result = ""

        # 添加第一个标签前的内容
        if separators:
            result += separators[0]

        # 重建每个标签，根据标签类型分别处理
        for i, tag_info in enumerate(tag_infos):
            # 重建标签
            if tag_info['tag_type'] == 'colon_tag':
                # 带冒号的标签
                if i < len(translated_parts):
                    translated_part = translated_parts[i]
                    restored_tag = (
                            tag_info['tag_prefix'] +
                            tag_info['content_leading_whitespace'] +
                            translated_part +
                            tag_info['content_trailing_whitespace'] +
                            tag_info['tag_suffix']
                    )
                else:
                    restored_tag = tag_info['tag_prefix'] + tag_info['tag_suffix']

            elif tag_info['tag_type'] == 'simple_tag':
                # 简单标签，直接使用原标签
                restored_tag = tag_info['full_tag']

            result += restored_tag

            # 添加标签后的分隔符（除了最后一个标签）
            if i + 1 < len(separators):
                result += separators[i + 1]

        return result

    def _restore_tag_content(self, content: str, tag_info: Dict) -> str:
        """统一标签还原入口"""
        if not tag_info:
            return content

        tag_type = tag_info.get('type')

        if tag_type == 'single_tag':
            return self._restore_single_tag_content(content, tag_info)
        elif tag_type == 'multiple_tags':
            return self._restore_multiple_tags(content, tag_info)

        return content

    def _normalize_line_endings(self, text: str) -> Tuple[str, List[Tuple[int, str]]]:
        """
        统一换行符为 \n，并记录每个换行符的原始类型和位置
        现在支持HTML换行标记：<br>, <br/>, <br />
        返回: (标准化后的文本, 换行符位置和类型列表)
        """
        if not ('\r' in text or '\n' in text or '<br' in text.lower()):
            return text, []

        # 记录每个换行符的位置和类型
        line_endings = []
        normalized_text = ""
        i = 0
        line_pos = 0  # 在标准化文本中的行位置

        while i < len(text):
            # 检查HTML <br> 标记（不区分大小写）
            if text[i:i + 3].lower() == '<br':
                # 找到完整的br标记
                br_end = text.find('>', i)
                if br_end != -1:
                    br_tag = text[i:br_end + 1]
                    line_endings.append((line_pos, br_tag))
                    normalized_text += '\n'
                    i = br_end + 1
                    line_pos += 1
                    continue

            # 检查传统换行符
            if i < len(text) - 1 and text[i:i + 2] == '\r\n':
                # Windows 换行符
                line_endings.append((line_pos, '\r\n'))
                normalized_text += '\n'
                i += 2
                line_pos += 1
            elif text[i] == '\r':
                # Mac 经典换行符
                line_endings.append((line_pos, '\r'))
                normalized_text += '\n'
                i += 1
                line_pos += 1
            elif text[i] == '\n':
                # Unix 换行符
                line_endings.append((line_pos, '\n'))
                normalized_text += '\n'
                i += 1
                line_pos += 1
            else:
                normalized_text += text[i]
                i += 1

        return normalized_text, line_endings

    def _restore_line_endings(self, text: str, line_endings: List[Tuple[int, str]]) -> str:
        """根据记录的换行符信息还原原始格式"""
        if not line_endings:
            return text

        lines = text.split('\n')
        if len(lines) <= 1:
            return text

        # 重建文本，使用对应的原始换行符
        result = []
        for i, line in enumerate(lines[:-1]):  # 最后一行后面没有换行符
            result.append(line)
            if i < len(line_endings):
                result.append(line_endings[i][1])
            else:
                result.append('\n')  # 默认使用 \n

        # 添加最后一行
        if lines:
            result.append(lines[-1])

        return ''.join(result)

    def _handle_special_characters(self, prefix: str, core_text: str, suffix: str) -> Tuple[str, str, str]:
        """处理特殊字符边界"""
        # 处理前缀
        if prefix:
            if prefix.endswith('['):
                core_text = '[' + core_text
                prefix = prefix[:-1]
            elif prefix.endswith('{'):
                core_text = '{' + core_text
                prefix = prefix[:-1]
            elif prefix.endswith('（'):
                core_text = '（' + core_text
                prefix = prefix[:-1]
            elif prefix.endswith('('):
                core_text = '(' + core_text
                prefix = prefix[:-1]

        # 处理后缀
        if suffix:
            if suffix.startswith(']'):
                core_text = core_text + ']'
                suffix = suffix[1:]
            elif suffix.startswith('}'):
                core_text = core_text + '}'
                suffix = suffix[1:]
            elif suffix.startswith('）'):
                core_text = core_text + '）'
                suffix = suffix[1:]
            elif suffix.startswith(')'):
                core_text = core_text + ')'
                suffix = suffix[1:]

        # 数字后缀处理
        if suffix and suffix.isdigit():
            core_text, suffix = core_text + suffix, ""

        return prefix, core_text, suffix

    def _process_multiline_text(self, text: str, source_lang: str) -> Tuple[str, Dict]:
        """处理多行文本（集成标签处理功能）"""

        # 第一步：检查并处理标签格式
        tag_processed_text, tag_info = self._process_tag_content(text)

        # 第二步：对处理后的文本进行原有的多行空白处理
        normalized_text, line_endings = self._normalize_line_endings(tag_processed_text)
        lines = normalized_text.split('\n')

        # 选择正则模式
        pattern = self.RE_WHITESPACE_AFFIX
        if source_lang == 'ja' or source_lang == 'japanese':
            pattern = self.RE_JA_AFFIX

        non_empty_lines = []  # 只存储非空行，用于翻译
        lines_info = []

        for line in lines:
            # 修改判断条件：检查空行或纯空白行
            if not line or not line.strip():  # 空行或纯空白行处理
                lines_info.append({
                    'prefix': '',
                    'suffix': '',
                    'is_empty': True,
                    'original_whitespace': line  # 保存原始空白字符
                })
                continue

            match = pattern.match(line)
            if match:
                prefix, core_text, suffix = match.group(1), match.group(2), match.group(3)

                # 应用特殊字符处理
                prefix, core_text, suffix = self._handle_special_characters(prefix, core_text, suffix)

                # 确保核心内容不为空
                if not core_text.strip() and line.strip():
                    core_text, prefix, suffix = line, '', ''

                # 检查前缀 (去除首尾空格后判断是否为数字)
                if prefix.strip().isdigit():
                    # 只保留前导空白作为前缀
                    prefix_leading = prefix[:len(prefix) - len(prefix.lstrip())]
                    core_text = prefix[len(prefix_leading):] + core_text  # 数字+紧邻空白都合并
                    prefix = prefix_leading

                # 检查后缀
                if suffix.strip().isdigit():
                    # 只保留后尾空白作为后缀
                    suffix_trailing = suffix[len(suffix.rstrip()):]
                    core_text = core_text + suffix[:len(suffix) - len(suffix_trailing)]  # 数字+紧邻空白都合并
                    suffix = suffix_trailing

                non_empty_lines.append(core_text)
                lines_info.append({'prefix': prefix, 'suffix': suffix, 'is_empty': False})
            else:
                non_empty_lines.append(line)
                lines_info.append({'prefix': '', 'suffix': '', 'is_empty': False})

        # 返回用于翻译的文本（不包含空行和纯空白行）
        processed_text = '\n'.join(non_empty_lines)

        # 构建处理信息
        info = {
            'type': 'multiline_with_tag' if tag_info else 'multiline',
            'line_endings': line_endings,
            'lines_info': lines_info,
            'tag_info': tag_info
        }

        return processed_text, info

    def _create_empty_info(self) -> Dict:
        """创建空的处理信息"""
        return {
            'type': 'single',
            'line_ending': '\n',
            'lines_info': [{'prefix': '', 'suffix': '', 'is_empty': False}],
            'tag_info': None
        }

    def _restore_multiline_text(self, text: str, info: Dict) -> str:
        """还原多行文本（集成标签还原功能）"""

        # 第一步：还原多行和空白格式
        translated_lines = text.split('\n')
        lines_info = info.get('lines_info', [])
        line_endings = info.get('line_endings', [])

        # 验证翻译结果行数是否正确
        expected_translated_count = sum(1 for line_info in lines_info
                                        if not line_info.get('is_empty', False))

        if len(translated_lines) != expected_translated_count:
            print(f"[Warning]: 翻译前后行数不匹配! 期望{expected_translated_count}行，实际{len(translated_lines)}行")

        restored_lines = []
        translated_index = 0

        for line_info in lines_info:
            if line_info.get('is_empty', False):
                # 还原空行或纯空白行
                original_whitespace = line_info.get('original_whitespace', '')
                restored_lines.append(original_whitespace)
            else:
                # 还原非空行
                if translated_index < len(translated_lines):
                    line = translated_lines[translated_index]
                    prefix = line_info.get('prefix', '')
                    suffix = line_info.get('suffix', '')
                    restored_lines.append(f"{prefix}{line}{suffix}")
                    translated_index += 1
                else:
                    # 防护措施：如果翻译结果不够，使用空字符串
                    restored_lines.append('')

        multiline_restored = '\n'.join(restored_lines)
        multiline_restored = self._restore_line_endings(multiline_restored, line_endings)

        # 第二步：如果有标签信息，还原标签格式
        tag_info = info.get('tag_info')
        if tag_info:
            return self._restore_tag_content(multiline_restored, tag_info)

        return multiline_restored

    def _compile_translation_rules(self, rules_data: Optional[List[Dict]]) -> List[Dict]:
        compiled_rules = []
        if not rules_data:
            return compiled_rules

        # 遍历文本替换的数据
        for rule in rules_data:
            new_rule = rule.copy()

            # 如果有正则，则进行预编译，如果没有则原样
            if regex_str := rule.get("regex"):
                new_rule["compiled_regex"] = re.compile(regex_str)

            compiled_rules.append(new_rule)
        return compiled_rules

    def _prepare_code_pattern_strings(self, exclusion_list_data: Optional[List[Dict]], regex_dir_path: str) -> List[
        str]:
        patterns: List[str] = []

        # 读取正则库内容
        with open(regex_dir_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            file_patterns = [item["regex"] for item in data
                             if isinstance(item, dict) and "regex" in item and item["regex"]]
        patterns.extend(file_patterns)

        # 读取禁翻表内容
        if exclusion_list_data:
            for item in exclusion_list_data:
                if regex_str := item.get("regex"):
                    if regex_str: patterns.append(regex_str)
                elif markers := item.get("markers"):
                    if markers: patterns.append(re.escape(markers))
        return patterns

    def _build_dynamic_pattern_strings(self, base_patterns: List[str], format_string: str) -> List[str]:
        """辅助函数，用于基于基础模式列表和格式化字符串构建增强的模式字符串(例如，在模式两侧添加空白匹配)"""
        enhanced_patterns = []
        if base_patterns:
            for p in base_patterns:
                if p:
                    try:
                        enhanced = format_string.format(p=p)
                        enhanced_patterns.append(enhanced)
                    except KeyError:
                        enhanced_patterns.append(p)
        return enhanced_patterns

    # 译前文本处理
    def replace_all(self, config, source_lang: str, text_dict: Dict[str, str]) -> \
            Tuple[Dict[str, str], Dict, Dict, Dict, Dict]:
        # 存储处理后信息的变量
        processed_text = {k: v for k, v in text_dict.items()}
        prefix_codes: Dict[str, List[Dict]] = {}
        suffix_codes: Dict[str, List[Dict]] = {}
        placeholder_order: Dict[str, List[Dict[str, str]]] = {}
        affix_whitespace_storage: Dict[str, Dict] = {}

        # 获取各个配置信息,减少再次传递
        pre_translation_switch = config.pre_translation_switch
        auto_process_text_code_segment = config.auto_process_text_code_segment
        target_platform = config.target_platform

        # 译前替换
        if pre_translation_switch:
            processed_text = self.replace_before_translation(processed_text)

        # 空白换行，非日语文本前后缀处理（支持多行）
        processed_text, affix_whitespace_storage = self.strip_and_record_affixes(processed_text, source_lang)

        # 自动预处理
        if auto_process_text_code_segment:
            # 自动处理前后缀
            processed_text, prefix_codes, suffix_codes = self._process_affixes(
                processed_text,
                self.auto_compiled_patterns,
                self.auto_compiled_patterns
            )

            # 自动处理文本中间内容
            processed_text, placeholder_order = self._replace_special_placeholders(
                target_platform,
                processed_text,
                self.auto_compiled_patterns
            )

        # 处理数字序号
        processed_text = self.digital_sequence_preprocessing(processed_text)

        return processed_text, prefix_codes, suffix_codes, placeholder_order, affix_whitespace_storage

    # 译后文本处理
    def restore_all(self, config, text_dict: Dict[str, str], prefix_codes: Dict, suffix_codes: Dict,
                    placeholder_order: Dict, affix_whitespace_storage: Dict) -> Dict[str, str]:
        restored = text_dict.copy()

        # 获取各个配置信息
        auto_process_text_code_segment = config.auto_process_text_code_segment
        post_translation_switch = config.post_translation_switch

        # 自动处理还原
        if auto_process_text_code_segment:
            restored = self._restore_special_placeholders(restored, placeholder_order)
            restored = self._restore_affixes(restored, prefix_codes, suffix_codes)

        # 译后替换
        if post_translation_switch:
            restored = self.replace_after_translation(restored)

        # 数字序号还原
        restored = self.digital_sequence_recovery(restored)

        # 前后空白换行，非日语文本还原（支持多行）
        restored = self.restore_affix_whitespace(affix_whitespace_storage, restored)

        return restored

    # 处理并占位文本中间内容
    def _replace_special_placeholders(self, target_platform: str, text_dict: Dict[str, str],
                                      compiled_placeholder_patterns: List[re.Pattern]) -> \
            Tuple[Dict[str, str], Dict[str, List[Dict[str, str]]]]:
        new_dict = {}
        placeholder_order: Dict[str, List[Dict[str, str]]] = {}
        global_match_count = 0

        for key, original_text in text_dict.items():
            current_text = original_text
            entry_placeholders: List[Dict[str, str]] = []
            sakura_match_count = 0

            for pattern_obj in compiled_placeholder_patterns:
                single_pattern_replacements: List[Dict[str, str]] = []

                def replacer_for_this_pattern(match_obj):
                    nonlocal global_match_count, sakura_match_count, single_pattern_replacements

                    if global_match_count >= 50:
                        return match_obj.group(0)

                    global_match_count += 1
                    sakura_match_count += 1
                    original_match_val = match_obj.group(0)

                    placeholder_val = f"[P{global_match_count}]"
                    if target_platform == "sakura":
                        placeholder_val = "↓" * sakura_match_count

                    single_pattern_replacements.append({
                        "placeholder": placeholder_val,
                        "original": original_match_val,
                        "pattern": pattern_obj.pattern
                    })
                    return placeholder_val

                try:
                    current_text = pattern_obj.sub(replacer_for_this_pattern, current_text)
                    entry_placeholders.extend(single_pattern_replacements)
                except Exception as e:
                    print(f"[Warning]: 占位正则替换出现问题！！ pattern '{pattern_obj.pattern}' on key '{key}': {e}")
                    continue

                if global_match_count >= 50:
                    break

            placeholder_order[key] = entry_placeholders
            new_dict[key] = current_text

        return new_dict, placeholder_order

    # 还原特殊占位符
    def _restore_special_placeholders(self, text_dict: Dict[str, str],
                                      placeholder_order: Dict[str, List[Dict[str, str]]]) -> Dict[str, str]:
        new_dic = {}
        for key, text in text_dict.items():
            placeholders_for_key = placeholder_order.get(key, [])

            if not placeholders_for_key:
                new_dic[key] = text
            else:
                restored_text = text
                for item in reversed(placeholders_for_key):
                    placeholder_text = item.get("placeholder")
                    original_text_val = item.get("original")
                    if placeholder_text is not None and original_text_val is not None:
                        if placeholder_text in restored_text:
                            restored_text = restored_text.replace(placeholder_text, original_text_val, 1)
                        else:
                            print(
                                f"[Warning]: Placeholder '{placeholder_text}' not found in text for key '{key}' during restoration. Original: '{original_text_val}'")
                new_dic[key] = restored_text
        return new_dic

    # 处理前后缀
    def _process_affixes(self, text_dict: Dict[str, str], compiled_prefix_patterns: List[re.Pattern],
                         compiled_suffix_patterns: List[re.Pattern]) -> \
            Tuple[Dict[str, str], Dict[str, List[Dict]], Dict[str, List[Dict]]]:
        prefix_codes: Dict[str, List[Dict]] = {}
        suffix_codes: Dict[str, List[Dict]] = {}
        processed_text_dict = {}

        for key, text_val in text_dict.items():
            current_text = text_val
            current_prefixes: List[Dict] = []
            current_suffixes: List[Dict] = []

            for pattern_obj in compiled_prefix_patterns:
                try:
                    while True:
                        match = pattern_obj.match(current_text)
                        if match:
                            prefix_text = match.group(0)
                            current_prefixes.append({"prefix": prefix_text, "pattern": pattern_obj.pattern})
                            current_text = current_text[len(prefix_text):]
                        else:
                            break
                except Exception as e:
                    print(
                        f"[Warning]: 前缀正则匹配出现问题！！ Regex error for prefix pattern '{pattern_obj.pattern}' on key '{key}': {e}")
                    continue

            # 遍历预编译的后缀正则表达式
            for pattern_obj in compiled_suffix_patterns:
                try:
                    made_change = True
                    while made_change:
                        made_change = False
                        best_match = None
                        for match in pattern_obj.finditer(current_text):
                            if match.end() == len(current_text):
                                best_match = match
                        if best_match:
                            suffix_text = best_match.group(0)
                            current_suffixes.insert(0, {"suffix": suffix_text, "pattern": pattern_obj.pattern})
                            current_text = current_text[:best_match.start()]
                            made_change = True
                except Exception as e:
                    print(
                        f"[Warning]: 后缀正则匹配出现问题！！ Regex error for suffix pattern '{pattern_obj.pattern}' on key '{key}': {e}")
                    continue

            # 特殊情况：如果移除前后缀后，中间的核心文本变为空白内容，还原最少内容的前后缀。
            if not current_text.strip():
                temp_prefix_str = ''.join([p['prefix'] for p in current_prefixes])
                temp_suffix_str = ''.join([s['suffix'] for s in current_suffixes])
                if current_prefixes and current_suffixes:
                    prefix_len = sum(len(p['prefix']) for p in current_prefixes)
                    suffix_len = sum(len(s['suffix']) for s in current_suffixes)
                    if prefix_len > suffix_len:
                        current_text = current_text + temp_suffix_str
                        current_suffixes = []
                    else:
                        current_text = temp_prefix_str + current_text
                        current_prefixes = []
                elif current_prefixes:
                    current_text = temp_prefix_str + current_text
                    current_prefixes = []
                elif current_suffixes:
                    current_text = current_text + temp_suffix_str
                    current_suffixes = []

            processed_text_dict[key] = current_text
            prefix_codes[key] = current_prefixes
            suffix_codes[key] = current_suffixes

        return processed_text_dict, prefix_codes, suffix_codes

    # 还原前后缀
    def _restore_affixes(self, text_dict: Dict[str, str], prefix_codes: Dict[str, List[Dict]],
                         suffix_codes: Dict[str, List[Dict]]) -> Dict[str, str]:
        restored_dict = {}
        for key, text in text_dict.items():
            # 按原始顺序拼接所有提取的前缀
            prefix_str = ''.join([item['prefix'] for item in prefix_codes.get(key, [])])
            # 按原始顺序拼接所有提取的后缀
            suffix_str = ''.join([item['suffix'] for item in suffix_codes.get(key, [])])
            restored_dict[key] = f"{prefix_str}{text}{suffix_str}"
        return restored_dict

    # 译前替换处理
    def replace_before_translation(self, text_dict: dict) -> dict:
        processed_text_dict = text_dict.copy()

        for k, original_text_val in processed_text_dict.items():
            current_text = original_text_val

            # 遍历所有预编译的译前规则
            for rule in self.pre_translation_rules_compiled:
                compiled_regex_obj = rule.get("compiled_regex")
                src_text = rule.get("src")
                dst_text = rule.get("dst", "")

                # 如果有已经编译好的正则
                if compiled_regex_obj:
                    current_text = compiled_regex_obj.sub(dst_text, current_text)
                    continue

                # 没有正则，则按照原文替换
                elif src_text and src_text in current_text:
                    current_text = current_text.replace(src_text, dst_text)

            if current_text != original_text_val:
                processed_text_dict[k] = current_text

        return processed_text_dict

    # 译后替换处理
    def replace_after_translation(self, text_dict: dict) -> dict:
        processed_text_dict = text_dict.copy()

        for k, original_text_val in processed_text_dict.items():
            current_text = original_text_val

            # 遍历所有预编译的译后规则
            for rule in self.post_translation_rules_compiled:
                compiled_regex_obj = rule.get("compiled_regex")
                src_text = rule.get("src")
                dst_text = rule.get("dst", "")

                if compiled_regex_obj:
                    current_text = compiled_regex_obj.sub(dst_text, current_text)
                    continue

                elif src_text and src_text in current_text:
                    current_text = current_text.replace(src_text, dst_text)

            if current_text != original_text_val:
                processed_text_dict[k] = current_text

        return processed_text_dict

    # 处理数字序列
    def digital_sequence_preprocessing(self, text_dict: dict) -> dict:
        """
        遍历字典，仅当文本以 "数字." 格式开头时，将其替换为 "【数字】"。
        例如: "1. 这是标题" -> "【1】这是标题"
        """
        for k in text_dict:
            # 使用新的正则表达式，它只匹配字符串开头的 "数字." 模式
            # r'【\1】' 移除了原来的点号
            text_dict[k] = self.RE_DIGITAL_SEQ_PRE.sub(r'【\1】', text_dict[k], count=1)
        return text_dict

    # 还原数字序列
    def digital_sequence_recovery(self, text_dict: dict) -> dict:
        """
        遍历字典，仅当文本以 "【数字】" 格式开头时，将其还原为 "数字."。
        例如: "【1】这是标题" -> "1. 这是标题"
        """
        for k in text_dict:
            # 使用新的正则表达式，它只匹配字符串开头的 "【数字】" 模式
            # r'\1.' 将捕获到的数字后面加上点号
            text_dict[k] = self.RE_DIGITAL_SEQ_REC.sub(r'\1.', text_dict[k], count=1)
        return text_dict

    # 处理前后缀的空格与换行，以及非日语文本（支持多行）
    def strip_and_record_affixes(self, text_dict: Dict[str, str], source_lang: str) -> \
            Tuple[Dict[str, str], Dict[str, Dict]]:
        processed_text_dict: Dict[str, str] = {}
        processing_info: Dict[str, Dict] = {}

        for key, original_text in text_dict.items():
            # 检查是否是字符串
            if not isinstance(original_text, str):
                processed_text_dict[key] = original_text
                processing_info[key] = self._create_empty_info()
                continue

            # 统一使用多行处理
            processed_text, info = self._process_multiline_text(original_text, source_lang)
            processed_text_dict[key] = processed_text
            processing_info[key] = info

        return processed_text_dict, processing_info

    # 还原前后缀的空格与换行（支持多行）
    def restore_affix_whitespace(self, processing_info: Dict[str, Dict], processed_dict: Dict[str, str]) -> Dict[
        str, str]:
        restored_text_dict: Dict[str, str] = {}

        for key, core_text in processed_dict.items():
            info = processing_info.get(key)
            if not info:
                restored_text_dict[key] = core_text
                continue

            # 使用多行还原逻辑
            restored_text = self._restore_multiline_text(core_text, info)
            restored_text_dict[key] = restored_text

        return restored_text_dict
