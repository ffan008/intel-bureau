"""群聊图片与文档（负责人 B2）：取回附件、图片 OCR、文档正文提取。签名见 docs/V2_KNOWLEDGE.md §5。

- ``fetch_media(app_cfg, secrets, platform, attachment, dest_dir)``：按 ``attachment["extra"]["fetch"]``
  取回（格式见 ``bureau.media.fetch`` 模块说明），文件名 = sha256 前 16 位 + 扩展名，检查
  ``media.max_file_mb``，记录 mime / 宽高。没有 fetch 但 ``attachment["url"]`` 是公网 http(s) 链接时按 URL 下载。
- ``ocr_image(path, mode="windows"|"llm"|"off", settings=, secrets=)``：见 ``bureau.media.ocr``。
- ``extract_document(path, max_chars=20000)``：pdf / docx / xlsx / pptx / txt / md / csv / html。

所有函数都不抛异常：失败时返回 ok=False（带中文 error）或空串。
"""

from bureau.media.documents import extract_document
from bureau.media.fetch import fetch_media, sniff_type
from bureau.media.models import MediaResult
from bureau.media.ocr import ocr_image

__all__ = ["MediaResult", "fetch_media", "ocr_image", "extract_document", "sniff_type"]
