# Nanoskop: kendi sunucunuza kurulum

Bu paket, Nanoskop'u kurumun kendi Linux sunucusunda çalıştırmak için hazırlandı. Nanomedicine proje verisi pakete dahil (`seed/prepared.pkl.gz`), bu yüzden site ilk açılışta veriyle birlikte gelir. Ayrıca CSV yüklemeniz gerekmez.

> **Önemli:** `seed/prepared.pkl.gz` veri setinin tamamını içerir. Ham CSV ile aynı gizlilik düzeyinde saklayın: e-postayla göndermeyin, herkese açık bir depoya (GitHub vb.) koymayın.

## Sunucu gereksinimleri

- Linux sunucu (Ubuntu 22.04/24.04, Debian 12, RHEL 9 veya benzeri)
- En az 2 CPU, 4 GB RAM ve 5 GB disk
- Kurulum sırasında internet erişimi (paketleri indirmek için). Sunucu internete kapalıysa aşağıdaki "İnternetsiz sunucu" bölümüne bakın.
- Kullanıcıların erişeceği bir adres (ör. `nanoskop.kurum.gov.tr`) ve bu adres için bir HTTPS sertifikası

Uygulama sunucunun yalnızca kendi içinden erişilebilen 8000 numaralı portta çalışır. Kullanıcılara Nginx (ya da kurumun kendi reverse proxy'si) üzerinden HTTPS ile açılır.

---

## Yol A: Docker ile kurulum (önerilen)

```bash
# 1. Paketi sunucuya kopyalayıp açın
unzip nanoskop-sunucu.zip -d /opt && cd /opt/nanoskop-sunucu

# 2. Giriş kodlarını belirleyin
cp .env.example .env
nano .env        # NANOSKOP_ADMIN_PASSWORD ve NANOSKOP_VIEWER_CODE değerlerini değiştirin
chmod 600 .env

# 3. Başlatın (ilk kurulum birkaç dakika sürer)
docker compose up -d --build

# 4. Kontrol edin
docker compose ps            # "healthy" yazmalı
curl -I http://127.0.0.1:8000/login
```

Sunucu yeniden başlatılırsa uygulama da kendiliğinden açılır (`restart: unless-stopped`). Ayarlar, örnek kayıtlar ve erişim kaydı `nanoskop-data` adlı Docker biriminde kalır.

## Yol B: Docker olmadan kurulum (systemd)

Python 3.13 gerekir.

```bash
sudo useradd --system --home /var/lib/nanoskop nanoskop
sudo mkdir -p /opt/nanoskop /var/lib/nanoskop
sudo cp -r app static seed requirements.txt run.py prepare.py .env.example /opt/nanoskop/
cd /opt/nanoskop
sudo python3.13 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo cp .env.example .env && sudo nano .env      # kodları değiştirin
sudo chown -R nanoskop: /var/lib/nanoskop && sudo chmod 600 .env && sudo chown nanoskop .env
sudo cp deploy/nanoskop.service /etc/systemd/system/      # (paket klasöründen)
sudo systemctl daemon-reload && sudo systemctl enable --now nanoskop
sudo systemctl status nanoskop
```

---

## HTTPS ile kullanıcılara açma (Nginx)

`deploy/nginx-nanoskop.conf` dosyasında alan adını ve sertifika yollarını değiştirin:

```bash
sudo cp deploy/nginx-nanoskop.conf /etc/nginx/sites-available/nanoskop
sudo ln -s /etc/nginx/sites-available/nanoskop /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Kurumda merkezi bir reverse proxy ya da yük dengeleyici varsa bilgi işlem birimi bu dosyayı örnek alabilir. Gereken ayarlar şunlar: `127.0.0.1:8000` adresine yönlendirme, `X-Real-IP` başlığı, 300 MB yükleme sınırı ve 300 saniye zaman aşımı.

Site yalnızca kurum içi ağdan, **HTTPS olmadan** açılacaksa `.env` dosyasında `NANOSKOP_SECURE_COOKIE=0` yapın. Aksi halde giriş çalışmaz. İnternete açık bir sunucuda bu değer her zaman `1` kalmalı.

## Kullanıcılara ne verilir

- Adres: `https://nanoskop.kurum.gov.tr`
- Görüntüleyici kodu (`NANOSKOP_VIEWER_CODE`)

Yönetici parolasını yalnızca siz kullanın. Yönetim sayfası: `https://.../admin`.

## Vercel sürümünden farklar

Kendi sunucunuzda tüm özellikler açıktır:

- **Veriyi güncelleme:** Yönetim sayfasından yeni CSV yüklenebilir. Özetler birkaç saniyede, küme haritası birkaç dakikada hazırlanır.
- **Gizlilik ayarları:** En küçük hücre ve en küçük filtre gibi eşikler yönetim sayfasından değiştirilebilir.
- **Örnek kayıtlar:** Yönetim sayfasından yeniden çekilebilir.
- **Alan görünürlüğü:** Her alanın ne kadarının gösterileceği yönetim sayfasından ayarlanabilir.
- **Kendi dosyasını yükleme:** Kullanıcılar 50 MB'a kadar dosya yükleyebilir. 30.000 satıra kadar olan dosyalar için küme haritası da çıkar.

`.env` dosyasındaki kodlar yalnızca **ilk açılışta** kullanılır. Sonradan kodu değiştirmek için yönetim sayfasını kullanın; `.env` dosyasını değiştirmek o aşamada etkisizdir. Kodu değiştirdiğinizde açık olan tüm oturumlar kapanır.

## Günlük işler

| İş | Docker | systemd |
|---|---|---|
| Durumu görmek | `docker compose ps` | `systemctl status nanoskop` |
| Uygulama günlüğü | `docker compose logs -f` | `journalctl -u nanoskop -f` |
| Erişim kaydı (her sorgu) | `docker compose exec nanoskop tail -f /data/access.log` | `tail -f /var/lib/nanoskop/access.log` |
| Yeniden başlatmak | `docker compose restart` | `systemctl restart nanoskop` |
| Kod güncellemek | yeni paketi açıp `docker compose up -d --build` | dosyaları değiştirip `systemctl restart nanoskop` |
| Yedek | `nanoskop-data` birimi | `/var/lib/nanoskop` klasörü |

## İnternetsiz sunucu

İmajı internete bağlı bir makinede hazırlayıp dosya olarak taşıyın:

```bash
# internete bağlı makinede
docker compose build && docker save nanoskop:latest | gzip > nanoskop-image.tar.gz
# sunucuda (paket klasörüyle birlikte)
docker load < nanoskop-image.tar.gz && docker compose up -d
```

## Notlar

- Uygulama **tek işlem** olarak çalışmalı (`--workers 1`). Kullanıcıların yüklediği dosyalar belleğin içinde tutulur.
- Kullanıcıların yüklediği kendi dosyaları diske yazılmaz. Bu dosyalar çıkış yapıldığında ya da 12 saat kullanılmadığında silinir. Uygulama yeniden başlatılırsa da kaybolur.
- Proje verisinin klasörü (`/data` ya da `/var/lib/nanoskop`) ham veriyi şifrelenmemiş olarak tutar. Sunucuya ve yedeklere erişimi buna göre sınırlayın.






printf 'NANOSKOP_ADMIN_PASSWORD=2UHdagFXVjBl8v6H\nNANOSKOP_VIEWER_CODE=UZb5gt2NvsTP\nNANOSKOP_SECURE_COOKIE=1\nNANOSKOP_MY_MAX_MB=50\nNANOSKOP_PORT=8100\n' > .env
chmod 600 .env
rm -f data/config.json data/sample.json
ls -la .env seed

cd ~/Desktop/nanoskop
printf 'NANOSKOP_ADMIN_PASSWORD=2UHdagFXVjBl8v6H\nNANOSKOP_VIEWER_CODE=UZb5gt2NvsTP\nNANOSKOP_SECURE_COOKIE=1\nNANOSKOP_MY_MAX_MB=50\nNANOSKOP_PORT=8000\n' > .env
chmod 600 .env
rm -f data/config.json






set -a; . ./.env; set +a
NANOSKOP_PREPARED=$PWD/seed/prepared.pkl.gz NANOSKOP_SECURE_COOKIE=0 .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000


cd ~/Desktop/nanoskop
set -a; . ./.env; set +a
NANOSKOP_PREPARED=$PWD/seed/prepared.pkl.gz NANOSKOP_SECURE_COOKIE=0 .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100



UZb5gt2NvsTP



cd ~/Desktop/nanoskop && ls -la seed && .venv/bin/python -c "
import gzip,pickle
p=pickle.load(gzip.open('seed/prepared.pkl.gz','rb'))
print('VERI TAMAM:', p['ds'].n, 'kayit')"




cd ~/Desktop/nano/nanoskop && ls -la seed && .venv/bin/python -c "
import gzip,pickle
p=pickle.load(gzip.open('seed/prepared.pkl.gz','rb'))
print('VERI TAMAM:', p['ds'].n, 'kayit')"




cd ~/Desktop/nano/nanoskop
set -a; . ./.env; set +a
export NANOSKOP_PREPARED=~/Desktop/nano/nanoskop/seed/prepared.pkl.gz
NANOSKOP_SECURE_COOKIE=0 .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100



printf'NANOSKOP_ADMIN_PASSWORD=2UHdagFXVjBl8v6H\nNANOSKOP_VIEWER_CODE=UZb5gt2NvsTP\nNANOSKOP_SECURE_COOKIE=1\nNANOSKOP_MY_MAX_MB=50\nNANOSKOP_PORT=8100\n' > .env
chmod 600 .env
rm -f data/config.json data/sample.json
ls -la .env seed



printf 'NANOSKOP_ADMIN_PASSWORD=2UHdagFXVjBl8v6H\nNANOSKOP_VIEWER_CODE=UZb5gt2NvsTP\nNANOSKOP_SECURE_COOKIE=1\nNANOSKOP_MY_MAX_MB=50\nNANOSKOP_PORT=8100\n' > .env
chmod 600 .env
rm -f data/config.json data/sample.json
ls -la .env seed






cd ~/Desktop/nano/nanoskop && ls -la seed && .venv/bin/python -c "
import gzip,pickle
p=pickle.load(gzip.open('seed/prepared.pkl.gz','rb'))
print('VERI TAMAM:', p['ds'].n, 'kayit')"




cd ~/Desktop/nano/nanoskop
set -a; . ./.env; set +a
export NANOSKOP_PREPARED=$HOME/Desktop/nano/nanoskop/seed/prepared.pkl.gz
NANOSKOP_SECURE_COOKIE=0 .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
cd ~/Desktop/nano/nanoskop
export NANOSKOP_ADMIN_PASSWORD=2UHdagFXVjBl8v6H
export NANOSKOP_VIEWER_CODE=UZb5gt2NvsTP
export NANOSKOP_PREPARED=$HOME/Desktop/nano/nanoskop/seed/prepared.pkl.gz
export NANOSKOP_SECURE_COOKIE=0
rm -f data/config.json data/sample.json
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100






cd ~/Desktop/nano/nanoskop && rm -f data/config.json data/sample.json && NANOSKOP_ADMIN_PASSWORD=2UHdagFXVjBl8v6H NANOSKOP_VIEWER_CODE=UZb5gt2NvsTP NANOSKOP_PREPARED=$HOME/Desktop/nano/nanoskop/seed/prepared.pkl.gz NANOSKOP_SECURE_COOKIE=0 .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
