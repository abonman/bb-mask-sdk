# bb-mask

Türkçe hukuki metindeki kişisel veriyi etiketler, model cevabındaki etiketleri geri açar. Paket ince bir HTTP istemcisidir. Model çağırmaz, metin yazdırmaz, bekletmez.

Müşteri Data Mask konsolundan `dm_test_` anahtarı alır. Kendi backend’i bu paketi kurar ve anahtarı `init`’e verir. LLM satırı müşterinindir; SDK’nın öncesine `anonymize`, sonrasına `restore` konur.

```python
import os
import bb_mask

bb_mask.init(api_key=os.environ["BB_ANONYM_TOKEN"])


def ozetle(metin: str) -> str:
    tagged = bb_mask.anonymize(metin)
    cevap = kendi_llm(tagged.text)                 # bu satır sizde
    return bb_mask.restore(tagged.doc_id, cevap)
```

Python 3.11+. Tek bağımlılık `httpx`. Bu depo yalnız Python paketidir. Go, .NET ve Node bu repoda yoktur.

## Kurulum

Paket yayınlanınca:

```bash
pip install bb-mask
```

Yayın öncesi, bu depoyu çektikten sonra:

```bash
pip install -e .
```

Anahtarı koda veya repoya yazmayın. Ortam değişkeni veya kendi ayar dosyanız yeter.

```bash
export BB_ANONYM_TOKEN="dm_test_..."
```

`init` süreçte bir kez çalışır. Model çağrısı değildir. Modül fonksiyonları (`bb_mask.anonymize` ve diğerleri) bundan önce çağrılırsa `BBError(401)` verir ve servise gitmez.

```python
istemci = bb_mask.init(
    api_key=os.environ["BB_ANONYM_TOKEN"],
    base_url="http://127.0.0.1:8081",  # varsayılan budur
    timeout=120,                       # saniye
)
```

| Argüman | Tip | Anlam |
|---|---|---|
| `api_key` | `str` | Konsoldaki `dm_test_` anahtarı. Boşsa `BBError(401)`. |
| `base_url` | `str` | Servis adresi. Varsayılan `http://127.0.0.1:8081`. |
| `timeout` | `float` | HTTP zaman aşımı, saniye. Varsayılan `120`. |

Dönüş `BBAnonym`'dur. Modül fonksiyonları bu istemciyi kullanır. İkinci `init` öncekinin yerine geçer.

İkinci bir anahtar gerekiyorsa süreç globaline dokunmadan `BBAnonym` kurun. Kurucu `init` istemez.

```python
diger = bb_mask.BBAnonym("http://127.0.0.1:8081", token, timeout=120)
```

## Nesneler

### `Tagged`

`anonymize`, `anonymize_file` ve `anonymize_documents` bunu döner.

| Alan | Tip | Ne zaman dolu |
|---|---|---|
| `text` | `str` | Her zaman. Kişisel veri yerine etiket vardır: `<PERSON_0>`, `<TR_NATIONAL_ID_0>`. |
| `doc_id` | `str \| None` | `persist=True` (varsayılan). Haritanın servisteki anahtarı. |
| `state` | `dict \| None` | `persist=False`. Haritanın kendisi. Servise yazılmaz. |

```python
tagged = bb_mask.anonymize("Davacı Hasan Demirkol, TC 62601815964")
tagged.doc_id   # "a1b2..."
tagged.text     # "Davacı <PERSON_0>, TC <TR_NATIONAL_ID_0>"
tagged.state    # None
```

Etiket biçimi `<TIP_0>`. Aynı yüzey aynı numarayı alır. Model etiketi bozarsa (`<PERSON 0>`) onarım servistedir. Mahkeme ve kanun adları etiketlenmez.

### `state` / `get_map` sözlüğü

Şekil: `dict[str, dict[str, str]]`. Dış anahtar varlık tipi, iç anahtar düz metin, değer etikettir.

```python
{
    "PERSON": {"Hasan Demirkol": "<PERSON_0>"},
    "TR_NATIONAL_ID": {"62601815964": "<TR_NATIONAL_ID_0>"},
}
```

Sözlük düz isim taşır. Loga, bilete veya modele koymayın. `restore` bu sözlüğü kendisi kullanır; modele yalnız `tagged.text` gider.

### `BBError`

`RuntimeError` alt sınıfı. `status_code: int`, `detail: str`. `str(hata)` ayrıntı metnidir.

| Kod | Anlam |
|---|---|
| 400 | Boş metin, 1–3 dışı dosya sayısı, oturumda anonymize yok, `doc_id` ve `state` ikisi de yok. |
| 401 | `init` çağrılmadı, anahtar boş veya tanınmıyor. |
| 402 | Bakiye yok. Anonimleştirme servise gitmez. |
| 404 | Harita yok. Silinmiş, `once=True` ile okunmuş veya servis tutmuyordur. |
| 413 | Dosya 20 MB üstü. |
| 501 | `complete` ailesi. Bu uç henüz açık değil. |

Ücret başarılı anonymize çağrısında düşer. Servis hata verirse ücret geri yazılır. `restore`, `get_map` ve `delete` ücret yazmaz.

### `MaskSession`

`with bb_mask.session()` bunu verir. `doc_id` ve `state` oturumun içindedir.

| Metod | Dönüş |
|---|---|
| `anonymize(text)` | `Tagged` |
| `anonymize_file(path)` | `Tagged`. Yolu okur. |
| `anonymize_documents(paths)` | `Tagged` |
| `restore(model_metni)` | `str` |
| `close()` | `None`. Blok bitince kendiliğinden çağrılır. |
| `persist` | `bool`. Kurgu 1 ise `True`. Oturumda sabittir. |

`restore` burada yalnız model metnini alır. Anonymize olmadan çağrılırsa `BBError(400)`. Blok bitince `close` çalışır: `persist=True` ise tutulan her `doc_id` silinir, `persist=False` ise state düşer ve servise silme gitmez.

## Çağrılar

Hepsi `init` sonrasında. Dosya uzantısı `.txt`, `.pdf` veya `.docx`. Dosya başına tavan 20 MB.

Modül düzeyinde `anonymize_file(path)` bir yol alır ve dosyayı okur; içeride `BBAnonym.anonymize_path` çağrılır. Bayt sizdeyse `BBAnonym.anonymize_file(filename, content)` kullanın. `MaskSession.anonymize_file(path)` de yolu okur.

### Kurgu 1 — harita serviste, siz `doc_id` tutarsınız

```python
tagged = bb_mask.anonymize(metin)
cevap = kendi_llm(tagged.text)
duz = bb_mask.restore(tagged.doc_id, cevap)
bb_mask.delete(tagged.doc_id)          # iş bitince
```

Tek dosya:

```python
tagged = bb_mask.anonymize_file("dilekce.pdf")
duz = bb_mask.restore(tagged.doc_id, kendi_llm(tagged.text))
```

Birden çok dosya tek `doc_id` paylaşır. Aynı kişi iki dosyada da `<PERSON_0>` olur. Üst sınır 3 dosyadır. Ücret tek anonymize’dir.

```python
tagged = bb_mask.anonymize_documents(
    ["dilekce.pdf", "cevap.docx", "ek.txt"]
)
duz = bb_mask.restore(tagged.doc_id, kendi_llm(tagged.text))
```

`restore` orijinal dosyayı almaz. Modelin yazdığı metindeki etiketleri açar.

### Kurgu 2 — aynı `doc_id`, üstüne sözlük

```python
tagged = bb_mask.anonymize(metin)
sozluk = bb_mask.get_map(tagged.doc_id)
# sozluk["PERSON"]["Hasan Demirkol"] == "<PERSON_0>"

duz = bb_mask.restore(tagged.doc_id, kendi_llm(tagged.text))
```

Okuyunca servisteki kopya da silinsin:

```python
sozluk = bb_mask.get_map(tagged.doc_id, once=True)
# bundan sonra restore ve get_map 404 döner
```

Sözlük gerekmiyorsa Kurgu 1 yeter.

### Kurgu 3 — harita sizde, servis saklamaz

`doc_id` boştur. `state` sözlüktür. Onu modele koymayın. Süreç ölünce de `restore` çalışsın diye `state`’i kendi tarafta saklayabilirsiniz.

```python
tagged = bb_mask.anonymize(metin, persist=False)
assert tagged.doc_id is None and tagged.state is not None

cevap = kendi_llm(tagged.text)
duz = bb_mask.restore(tagged.state, cevap)
```

Dosyada da aynıdır: `anonymize_file(yol, persist=False)`, `anonymize_documents(yollar, persist=False)`.

### Kurgu 4 — siz id veya json görmezsiniz

Kurgu 1. Çıkışta harita silinir.

```python
with bb_mask.session() as s:
    tagged = s.anonymize_documents(["dilekce.pdf", "ek.txt"])
    cevap = kendi_llm(tagged.text)
    duz = s.restore(cevap)
```

Kurgu 3 yüzeyi. State oturum nesnesindedir, servise yazılmaz.

```python
with bb_mask.session(persist=False) as s:
    tagged = s.anonymize(metin)
    duz = s.restore(kendi_llm(tagged.text))
```

### Kurgu 0 — `complete`

Adlar durur: `complete`, `complete_file`, `complete_documents`, `acomplete`. HTTP çağrısı yapmazlar. `init` yoksa `BBError(401)`, varsa `BBError(501)`. `BBAnonym` üzerindeki aynı metotlar doğrudan `501` verir.

### Async

Beş fonksiyon vardır. İmzalar senkron kardeşleriyle aynıdır. HTTP işi bir thread’de yürür. `init` bunlarda da gerekir.

```python
aanonymize(text, persist=True) -> Tagged
aanonymize_file(path, persist=True) -> Tagged
aanonymize_documents(paths, persist=True) -> Tagged
arestore(doc_id_or_state, model_text) -> str
acomplete(text) -> str
```

```python
tagged = await bb_mask.aanonymize(metin)
duz = await bb_mask.arestore(tagged.doc_id, cevap)
```

`get_map`, `delete`, `session`, `complete_file` ve `complete_documents` için async karşılık yoktur.

## Referans

Modül fonksiyonları `init` ister. `BBAnonym` metotları kurucudaki anahtarı kullanır.

### Modül

```python
init(api_key: str, base_url: str = "http://127.0.0.1:8081", timeout: float = 120) -> BBAnonym
anonymize(text: str, persist: bool = True) -> Tagged
anonymize_file(path: str | Path, persist: bool = True) -> Tagged
anonymize_documents(paths: list[str | Path], persist: bool = True) -> Tagged
restore(doc_id_or_state: str | dict, model_text: str) -> str
get_map(doc_id: str, once: bool = False) -> dict
delete(doc_id: str) -> bool
session(persist: bool = True)  # with ile MaskSession
complete(text: str) -> str
complete_file(path: str | Path) -> str
complete_documents(paths: list[str | Path]) -> str
aanonymize(text: str, persist: bool = True) -> Tagged
aanonymize_file(path: str | Path, persist: bool = True) -> Tagged
aanonymize_documents(paths: list[str | Path], persist: bool = True) -> Tagged
arestore(doc_id_or_state: str | dict, model_text: str) -> str
acomplete(text: str) -> str
```

`persist=True` haritayı serviste tutar, `Tagged.doc_id` dolar. `persist=False` haritayı yazmaz, `Tagged.state` dolar, `doc_id` `None` olur.

`restore` ilk argüman `doc_id` (`str`) veya `state` (`dict`). İkinci argüman modelin yazdığı metindir. Dönüş düz metindir.

`get_map` sözlüğü döner. `once=True` okuyunca servisteki kopyayı siler; bundan sonra `restore` ve `get_map` `404` verir.

`delete` servis `deleted` derse `True` döner.

`session` context manager'dır: `with bb_mask.session() as s`. Çıkışta `s.close()` çalışır.

`complete`, `complete_file`, `complete_documents` ve `acomplete` HTTP çağırmaz. `init` yoksa `401`, varsa `501`.

### `BBAnonym`

`init` gerekmez. Modüldeki `anonymize_file`'dan farklı olarak burada dosya ikiye ayrılır: ad ve bayt. Yolu okuyan metot `anonymize_path`'tir.

```python
BBAnonym(base_url: str, token: str, timeout: float = 120)
anonymize(text: str, persist: bool = True) -> Tagged
anonymize_file(filename: str, content: bytes, persist: bool = True) -> Tagged
anonymize_path(path: str | Path, persist: bool = True) -> Tagged
anonymize_documents(paths: list[str | Path], persist: bool = True) -> Tagged
restore(doc_id_or_state: str | dict, model_text: str) -> str
get_map(doc_id: str, once: bool = False) -> dict
delete(doc_id: str) -> bool
complete(text: str) -> str
complete_file(path: str | Path) -> str
complete_documents(paths: list[str | Path]) -> str
```

`complete` ailesi dosyayı okumaz; çağrı anında `BBError(501)` verir.

### `MaskSession`

Kurucu dışarıdan çağrılmaz. `persist` oturum açılırken verilir, metotlara tekrar geçilmez.

```python
anonymize(text: str) -> Tagged
anonymize_file(path: str | Path) -> Tagged
anonymize_documents(paths: list[str | Path]) -> Tagged
restore(model_text: str) -> str
close() -> None
```

## Bu pakette olmayanlar

- Müşterinin LLM çağrısı ve `@ask`.
- FastAPI uygulaması, konsol çıktısı, `sleep`.
- Anahtar üretimi ve bakiye. Onlar panelde.
- Etiket onarımı. Bozuk etiketi servis düzeltir; sözlükteki anahtar düz metindir.
