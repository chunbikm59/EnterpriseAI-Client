"""
PyMuPDF-based PDF converter for MarkItDown.
解決 pdfminer fallback 對 CIDFont 中文字型產生 \x00 亂碼的問題。
使用方式：
    md = MarkItDown(...)
    md.register_converter(PyMuPdfConverter(), priority=10.0)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO

from markitdown._base_converter import DocumentConverter, DocumentConverterResult, StreamInfo

if TYPE_CHECKING:
    pass


class PyMuPdfConverter(DocumentConverter):
    """用 PyMuPDF (fitz) 取代 pdfminer 進行 PDF 文字擷取，正確處理 CJK CIDFont 編碼。"""

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        ext = (stream_info.extension or "").lower()
        mime = (stream_info.mimetype or "").lower()
        return ext == ".pdf" or mime == "application/pdf"

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> DocumentConverterResult:
        import fitz  # PyMuPDF

        data = file_stream.read()
        doc = fitz.open(stream=data, filetype="pdf")
        pages: list[str] = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text.strip())
        doc.close()
        return DocumentConverterResult(markdown="\n\n".join(pages))
