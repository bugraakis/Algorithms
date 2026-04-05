# Civilization VI Discord Botu

Ses kanalındaki oyuncular için FFA ve Takımlı oyun kurulumu yapan Discord botu.

## Kurulum

```bash
pip install -r requirements.txt
cp .env.example .env
# .env dosyasını açıp DISCORD_TOKEN değerini doldur
python bot.py
```

## Discord Developer Portal Ayarları

Bot tokenini almak için:
1. https://discord.com/developers/applications → New Application
2. Bot sekmesi → Token kopyala → `.env` dosyasına yapıştır
3. Bot sayfasında şu **Privileged Gateway Intents**'leri aç:
   - **Server Members Intent**
   - **Message Content Intent**

## Komutlar

| Komut | Açıklama |
|-------|----------|
| `/civ` | FFA veya Takımlı seçim menüsü açar |
| `/ffa` | Ses kanaldaki herkesi etiketler, FFA listesi oluşturur |
| `/takim` | Kaç takım istediğini sorar, oyuncuları rastgele dağıtır |
| `/yardim` | Komut listesini gösterir |

## Nasıl Çalışır?

### FFA
- `/ffa` veya `/civ → FFA` butonuna bas
- Bot, o an bulunduğun ses kanaldaki tüm üyeleri **etiketler** ve listeler

### Takımlı
- `/takim` veya `/civ → Takımlı` butonuna bas
- Bot kaç takım istediğini sorar (2–6 takım, oyuncu sayısına göre)
- Oyuncular seçilen takım sayısına rastgele ve dengeli dağıtılır
