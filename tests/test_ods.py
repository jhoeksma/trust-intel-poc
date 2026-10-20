import io
import zipfile

from app.sources.ods import iter_ods, sheet_names

CONTENT = """<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet>
<table:table table:name="Ratings"><table:table-row><table:table-cell office:value-type="string"><text:p>Name</text:p></table:table-cell>
<table:table-cell office:value-type="string"><text:p>Score</text:p></table:table-cell><table:table-cell table:number-columns-repeated="3000"/></table:table-row>
<table:table-row><table:table-cell office:value-type="string"><text:p>Alpha</text:p></table:table-cell>
<table:table-cell office:value-type="float" office:value="3.5"><text:p>3.5</text:p></table:table-cell></table:table-row>
<table:table-row table:number-rows-repeated="1048000"><table:table-cell table:number-columns-repeated="3000"/></table:table-row></table:table>
<table:table table:name="Two"><table:table-row><table:table-cell table:number-columns-repeated="2"/>
<table:table-cell office:value-type="float" office:value="7"><text:p>7</text:p></table:table-cell></table:table-row></table:table>
</office:spreadsheet></office:body></office:document-content>"""


def _ods():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("content.xml", CONTENT)
    return b.getvalue()


def test_sheet_names_and_rows_skip_padding():
    data = _ods()
    assert sheet_names(data) == ["Ratings", "Two"]
    rows = list(iter_ods(data))
    assert rows == [("Ratings", ["Name", "Score"]), ("Ratings", ["Alpha", 3.5]), ("Two", ["", "", 7])]


def test_only_sheet_filter():
    assert [r for _, r in iter_ods(_ods(), only_sheet="Two")] == [["", "", 7]]
