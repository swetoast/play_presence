"""Bounded title and artwork resolution from one matching gamelist entry."""
from __future__ import annotations
import json, logging, os, re, stat, xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from .config import MetadataConfig
from .detection import SessionCandidate
_LOGGER=logging.getLogger(__name__)
_ROM_EXT={'.32x','.a26','.a52','.a78','.bin','.chd','.cue','.fds','.gb','.gba','.gbc','.gg','.iso','.md','.n64','.nds','.nes','.ngc','.pce','.rom','.sfc','.smc','.sms','.v64','.wad','.ws','.wsc','.z64'}
_ARCHIVE_EXT={'.zip','.7z','.rar','.tar','.gz','.bz2','.xz'}
_MEDIA_EXT={'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp'}
_TAG=re.compile(r"\s*(?:\((?:Europe|USA|Japan|World|Australia|Korea|Brazil|Canada|China|France|Germany|Italy|Spain|Sweden|Netherlands|Asia|En(?:,[A-Za-z]{2})*|Rev(?:ision)?(?:\s*[A-Z0-9]+)?|Beta(?:\s*\d+)?|Proto(?:type)?|Kiosk|Demo|Sample|Unl|v\d+(?:\.\d+)*)\)|\[(?:!|b|a\d*|f\d*|h\d*|o\d*|p\d*|t\d*|T[+-]?\w*|U|x|BIOS|Bad|Overdump)\])\s*$",re.I)
_ARTICLE=re.compile(r'^(.*),\s*(The|A|An)(\s*[-:].*)?$',re.I)
class MetadataError(ValueError): pass
@dataclass(frozen=True)
class ResolvedMetadata:
    title:str
    artwork:bytes|None=None
    artwork_content_type:str|None=None

def _metadata_context(c, cfg):
    root = Path(c.rom_root)
    rom = Path(c.rom_path)
    system = root / c.system_folder
    try:
        relative = rom.relative_to(system)
    except ValueError as exc:
        raise MetadataError("ROM is outside its normalized system folder") from exc
    if not relative.parts or ".." in relative.parts:
        raise MetadataError("ROM metadata key is invalid")
    key = "./" + PurePosixPath(*relative.parts).as_posix()
    return system / cfg.gamelist_filename, key, system, relative


def metadata_location(c, cfg):
    gamelist, key, _, _ = _metadata_context(c, cfg)
    return gamelist, key

def stream_gamelist_entry(path,key):
    try:
        context=ET.iterparse(path,events=('start','end')); root=None
        for event,el in context:
            if root is None and event=='start': root=el; continue
            if event!='end' or el.tag.rsplit('}',1)[-1]!='game': continue
            values={}
            for child in el:
                tag=child.tag.rsplit('}',1)[-1]
                if tag in {'path','name','image'} and child.text: values[tag]=child.text.strip()
            el.clear(); root.clear() if root is not None else None
            if values.get('path')==key: return values.get('name') or None, values.get('image') or None
    except (OSError,ET.ParseError) as e: raise MetadataError(type(e).__name__) from e
    return None,None

def stream_gamelist_title(path,key): return stream_gamelist_entry(path,key)[0]
def load_overrides(cfg):
    if cfg.overrides_file is None:return {}
    try:
        if cfg.overrides_file.stat().st_size>cfg.overrides_max_bytes: raise MetadataError('override file exceeds configured size limit')
        value=json.loads(cfg.overrides_file.read_text(encoding='utf-8'))
    except MetadataError: raise
    except (OSError,json.JSONDecodeError) as e: raise MetadataError(type(e).__name__) from e
    if not isinstance(value,dict): raise MetadataError('override file root must be an object')
    return {k:v.strip() for k,v in value.items() if isinstance(k,str) and isinstance(v,str) and ':./' in k and v.strip()}
def conservative_title(filename):
    name=Path(filename).name
    while True:
        suffix=Path(name).suffix.casefold()
        if suffix in _ARCHIVE_EXT or suffix in _ROM_EXT: name=name[:-len(suffix)]
        else: break
    name=re.sub(r'[_]+',' ',name)
    previous=None
    while name!=previous: previous=name; name=_TAG.sub('',name)
    name=re.sub(r'\s+',' ',name).strip(' ._-')
    match=_ARTICLE.match(name)
    if match: name=f"{match.group(2).title()} {match.group(1).strip()}{match.group(3) or ''}"
    return name or Path(filename).stem

def _image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _safe_artwork(path, system, max_bytes):
    fd = None
    try:
        resolved_system = system.resolve(strict=True)
        resolved_parent = path.parent.resolve(strict=True)
        resolved_parent.relative_to(resolved_system)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > max_bytes:
            return None
        with os.fdopen(fd, "rb", closefd=True) as handle:
            fd = None
            data = handle.read(max_bytes + 1)
        if len(data) != info.st_size:
            return None
        content_type = _image_type(data)
        if content_type is None:
            return None
        expected = _MEDIA_EXT.get(path.suffix.casefold())
        if expected != content_type:
            return None
        return data, content_type
    except (OSError, ValueError):
        return None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _artwork_candidates(system,relative,image):
    result=[]
    if image:
        p=PurePosixPath(image.removeprefix('./'))
        if p.parts and '..' not in p.parts: result.append(system.joinpath(*p.parts))
    local=relative
    archived=local.suffix.casefold() in _ARCHIVE_EXT
    if archived: local=local.with_suffix('')
    for ext in _MEDIA_EXT:
        media=Path(str(local)+ext) if archived else local.with_suffix(ext)
        result.append(system/'images'/media)
    return result

class TitleResolver:
    def __init__(self,cfg): self.config=cfg; self._overrides=None; self._override_error_reported=False
    def _get_overrides(self):
        if self._overrides is None:self._overrides=load_overrides(self.config)
        return self._overrides
    def resolve_metadata(self,c):
        gamelist,key,system,relative=_metadata_context(c,self.config); title=image=None
        try:title,image=stream_gamelist_entry(gamelist,key)
        except MetadataError as e:_LOGGER.warning('Metadata unavailable for system %s; using fallback (%s)',c.system_id,e)
        if not title:
            try:title=self._get_overrides().get(f'{c.system_id}:{key}')
            except MetadataError as e:
                if not self._override_error_reported:_LOGGER.warning('Title override file unavailable; using fallback (%s)',e);self._override_error_reported=True
        artwork=None
        for candidate in _artwork_candidates(system,relative,image):
            artwork=_safe_artwork(candidate,system,self.config.artwork_max_bytes)
            if artwork:break
        return ResolvedMetadata(title or conservative_title(c.rom_file),*(artwork or (None,None)))
    def resolve(self,c): return self.resolve_metadata(c).title
