# IDX Helper

Download laporan keuangan perusahaan tercatat dari IDX (Indonesia Stock Exchange).

## Fitur

- Download laporan keuangan per tahun dan periode (TW1/TW2/TW3/Tahunan)
- Filter file berdasarkan tipe (xlsx, pdf, zip, atau custom regex)
- Filter opsional per kode emiten, atau download semua
- Start/cancel download per emiten
- Tidak membutuhkan browser atau chromedriver

## Cara Menjalankan

```bash
pip install flet requests
flet run app.py
```

## Build Executable

```bash
flet build windows --product-name "IDX Helper"
flet build macos --product-name "IDX Helper"
```
