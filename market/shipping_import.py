"""有界 CSV/XLSX 值导入；不执行公式、宏或外部链接。整表校验成功后才可确认保存。"""
import csv
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
import posixpath
import zipfile
from xml.etree import ElementTree as ET
from django.core.exceptions import ValidationError
from .shipping import RATE_FIELDS, rate_payload
from .shipping_forms import ShippingRateForm

MAX_ROWS = 100
COLUMNS = [
    ('name', '报价名称'), ('carrier', '承运商'), ('origin', '始发国家'), ('destination', '目的国家'),
    ('currency', '币种'), ('method', '计费方式'), ('min_weight', '最低计费kg'), ('max_weight', '最高计费kg'),
    ('step_weight', '进位续重kg'), ('per_kg', '每公斤价格'), ('first_weight', '首重kg'),
    ('first_price', '首重价格'), ('step_price', '续重单位价格'), ('fixed_fee', '每票固定费'),
    ('fuel_basis', '燃油基数'), ('volume_divisor', '体积重系数'), ('effective_from', '生效日期'),
    ('effective_until', '失效日期'), ('source_url', '来源链接'), ('notes', '适用条件备注')]
HEADERS = [label for _, label in COLUMNS]
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def _xml(archive, path):
    raw = archive.read(path)
    text = raw.decode('utf-8-sig')
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValidationError('表格含不支持的 XML 声明。')
    return ET.fromstring(text)


def _xlsx_rows(raw):
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) > 100 or sum(i.file_size for i in infos) > 12 * 1024 * 1024:
            raise ValidationError('表格解压后过大，请只保留报价数据。')
        if len({i.filename for i in infos}) != len(infos) or any(i.flag_bits & 1 for i in infos):
            raise ValidationError('不支持加密或结构异常的表格。')
        workbook = _xml(archive, 'xl/workbook.xml')
        props = workbook.find('m:workbookPr', NS)
        epoch = datetime(1904, 1, 1) if props is not None and props.get('date1904') in ('1', 'true') else datetime(1899, 12, 30)
        sheets = workbook.findall('m:sheets/m:sheet', NS)
        sheet = next((s for s in sheets if s.get('name') == '物流报价'), sheets[0] if len(sheets) == 1 else None)
        if sheet is None:
            raise ValidationError('工作簿须有“物流报价”工作表，请使用下载模板。')
        relationships = _xml(archive, 'xl/_rels/workbook.xml.rels')
        relation = next((r for r in relationships if r.get('Id') == sheet.get(f'{{{REL}}}id')), None)
        if relation is None or relation.get('TargetMode') == 'External':
            raise ValidationError('报价工作表结构无效。')
        target = relation.get('Target', '')
        path = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        if not path.startswith('xl/worksheets/') or '..' in path:
            raise ValidationError('报价工作表路径无效。')
        if any(r.get('TargetMode') == 'External' for r in relationships) or any('externalLinks/' in i.filename for i in infos):
            raise ValidationError('表格不能包含外部链接。')
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            for item in _xml(archive, 'xl/sharedStrings.xml').findall('m:si', NS):
                strings.append(''.join(t.text or '' for t in item.iter(f'{{{NS["m"]}}}t')))
        root = _xml(archive, path)
        if root.find('m:mergeCells', NS) is not None:
            raise ValidationError('物流报价工作表不能含合并单元格。')
        rows = []
        used = set()
        for row in root.findall('m:sheetData/m:row', NS):
            number = int(row.get('r', '0'))
            if number < 1 or number in used:
                raise ValidationError('表格行号异常。')
            used.add(number)
            values = [''] * 40
            kinds = [''] * 40
            cells = set()
            for cell in row.findall('m:c', NS):
                address = cell.get('r', '')
                letters = address.rstrip('0123456789')
                col = 0
                for letter in letters:
                    if letter not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                        raise ValidationError('单元格位置无效。')
                    col = col * 26 + ord(letter) - ord('A') + 1
                if not col or address[len(letters):] != str(number):
                    raise ValidationError('单元格位置与行号不一致。')
                if col in cells:
                    raise ValidationError('表格含重复单元格位置。')
                cells.add(col)
                if cell.find('m:f', NS) is not None:
                    raise ValidationError(f'第 {number} 行含公式，请在 Excel 中复制并粘贴为数值后导入。')
                value = cell.findtext('m:v', default='', namespaces=NS)
                kind = cell.get('t', 'n')
                if kind == 's':
                    index = int(value)
                    if not 0 <= index < len(strings):
                        raise ValidationError('共享文本索引无效。')
                    value = strings[index]
                elif kind == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.iter(f'{{{NS["m"]}}}t'))
                elif kind in ('e', 'b'):
                    raise ValidationError(f'第 {number} 行含错误或布尔值，请填写报价数值或文字。')
                if col > 40:
                    raise ValidationError('自有报价表最多40列。')
                values[col - 1] = value
                kinds[col - 1] = kind
            if any(str(v).strip() for v in values):
                rows.append((number, values, kinds))
            if len(rows) > MAX_ROWS + 1:
                raise ValidationError(f'一次最多导入 {MAX_ROWS} 行报价。')
        width = max((max((i + 1 for i, v in enumerate(values) if str(v).strip()), default=0) for _, values, _ in rows), default=0)
        return {'rows': [(n, v[:width], k[:width]) for n, v, k in sorted(rows)], 'epoch': epoch.date().isoformat(), 'sheet_count': len(sheets)}


def read_rate_table(raw, filename):
    """保留原行号与单元格类型，日期仅在映射到日期字段后转换。"""
    if len(raw) > 2 * 1024 * 1024:
        raise ValidationError('文件不能超过 2 MB。')
    try:
        if filename.lower().endswith('.xlsx'):
            table = _xlsx_rows(raw)
        elif filename.lower().endswith('.csv'):
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw.decode('gb18030')
            reader = csv.reader(StringIO(text), strict=True)
            rows = []
            while True:
                number = reader.line_num + 1
                try:
                    row = next(reader)
                except StopIteration:
                    break
                if len(row) > 40:
                    raise ValidationError('自有报价表最多40列。')
                if any(v.strip() for v in row):
                    rows.append((number, row, [''] * len(row)))
                if len(rows) > MAX_ROWS + 1:
                    raise ValidationError(f'一次最多导入 {MAX_ROWS} 行报价。')
            table = {'rows': rows, 'epoch': None, 'sheet_count': 1}
        else:
            raise ValidationError('只支持 .xlsx / .csv 文件。')
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, OverflowError, InvalidOperation, UnicodeError, csv.Error, RuntimeError):
        raise ValidationError('无法读取表格，请使用未加密的 Excel 或 CSV。')
    rows = table['rows']
    if not rows:
        raise ValidationError('表格没有表头或报价数据。')
    headers = [str(v).strip() for v in rows[0][1]]
    if not headers or any(not h for h in headers) or len(set(headers)) != len(headers):
        raise ValidationError('表头不能重复或留空。')
    if headers != HEADERS and table['sheet_count'] != 1:
        raise ValidationError('自有表格只支持一个工作表；标准模板的说明表仍可保留。')
    if any(len(str(value)) > 2000 for _, values, _ in rows for value in values):
        raise ValidationError('单元格文字过长，最多2000字符。')
    table['headers'] = headers
    return table


def _mapped_value(value, kind, key, epoch, number):
    if key in ('effective_from', 'effective_until') and value:
        try:
            if kind == 'n':
                serial = Decimal(value)
                if serial != serial.to_integral_value() or not 1 <= serial <= 2958465:
                    raise ValueError
                value = (datetime.fromisoformat(epoch) + timedelta(days=int(serial))).date().isoformat()
            elif kind == 'd':
                value = value.split('T', 1)[0]
        except (ValueError, OverflowError, InvalidOperation, TypeError):
            raise ValidationError(f'第 {number} 行日期无效，请填写 yyyy-mm-dd。')
    return str(value).strip()


def validate_rate_rows(table, mapping, common):
    parsed, errors = [], []
    for number, values, kinds in table['rows'][1:]:
        if len(values) != len(table['headers']):
            errors.append(f'第 {number} 行：列数与表头不一致。')
            continue
        try:
            data = {key: _mapped_value(values[index], kinds[index], key, table['epoch'], number)
                    if index is not None else common.get(key, '') for key, index in mapping.items()}
        except ValidationError as exc:
            errors.extend(exc.messages)
            continue
        form = ShippingRateForm(data)
        if form.is_valid():
            parsed.append(rate_payload(form.cleaned_data))
        else:
            errors.append(f'第 {number} 行：' + '；'.join(f'{form.fields[key].label if key in form.fields else "报价"}：{"、".join(messages)}' for key, messages in form.errors.items()))
    if errors:
        raise ValidationError(errors[:10] + ([f'另有 {len(errors) - 10} 行错误。'] if len(errors) > 10 else []))
    if not parsed:
        raise ValidationError('没有报价数据，请填写真实报价；说明表不参与导入。')
    return parsed


def parse_rates(raw, filename):
    table = read_rate_table(raw, filename)
    if table['headers'] != HEADERS:
        raise ValidationError('表头须与下载模板一致；自有表格可在上传入口选择列映射。')
    return validate_rate_rows(table, {key: i for i, (key, _) in enumerate(COLUMNS)}, {})


def csv_template():
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADERS)
    return '\ufeff' + buffer.getvalue()
