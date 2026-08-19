"""Report templates seed data (in Turkish) for real estate valuation.
Each template contains:
  - id, name, description, icon
  - sections: ordered list of sections
  - fields: ordered list of fields the AI must collect from the user
"""

REPORT_TEMPLATES = [
    {
        "id": "konut",
        "name": "Konut Değerleme Raporu",
        "description": "Daire, müstakil ev veya villa için standart konut değerleme raporu.",
        "icon": "Home",
        "cost_per_message": 4.0,
        "avg_report_cost": 25.0,
        "sections": [
            "Rapor Özeti",
            "Gayrimenkulün Yeri ve Ulaşım",
            "Yapısal Özellikler",
            "Piyasa Analizi",
            "Değer Tespiti",
            "Sonuç ve Kanaat",
        ],
        "fields": [
            {"key": "ada_parsel", "label": "Ada / Parsel No", "type": "text"},
            {"key": "adres", "label": "Açık Adres", "type": "textarea"},
            {"key": "brut_alan", "label": "Brüt Alan (m²)", "type": "number"},
            {"key": "net_alan", "label": "Net Alan (m²)", "type": "number"},
            {"key": "oda_sayisi", "label": "Oda Sayısı (Ör. 3+1)", "type": "text"},
            {"key": "bina_yasi", "label": "Bina Yaşı", "type": "number"},
            {"key": "kat", "label": "Bulunduğu Kat", "type": "text"},
            {"key": "isitma", "label": "Isıtma Sistemi", "type": "text"},
            {"key": "cevre_ozellikleri", "label": "Çevre / Sosyal Donatılar", "type": "textarea"},
            {"key": "emsal_fiyat", "label": "Emsal Birim Fiyat (TL/m²)", "type": "number"},
        ],
    },
    {
        "id": "ticari",
        "name": "Ticari Gayrimenkul Değerleme",
        "description": "Ofis, dükkan, plaza veya AVM ünitesi için ticari değerleme.",
        "icon": "Building2",
        "cost_per_message": 6.0,
        "avg_report_cost": 40.0,
        "sections": [
            "Rapor Özeti",
            "Lokasyon Analizi",
            "Yapı ve Kullanım Bilgileri",
            "Kira / Gelir Analizi",
            "Piyasa Karşılaştırması",
            "Değer Tespiti",
            "Sonuç",
        ],
        "fields": [
            {"key": "ada_parsel", "label": "Ada / Parsel No", "type": "text"},
            {"key": "adres", "label": "Açık Adres", "type": "textarea"},
            {"key": "kullanim_amaci", "label": "Kullanım Amacı (Ofis/Dükkan/Depo)", "type": "text"},
            {"key": "brut_alan", "label": "Brüt Alan (m²)", "type": "number"},
            {"key": "cephe", "label": "Cephe / Vitrin Uzunluğu (m)", "type": "number"},
            {"key": "kat", "label": "Bulunduğu Kat", "type": "text"},
            {"key": "aylik_kira", "label": "Aylık Kira Bedeli (TL)", "type": "number"},
            {"key": "kapitalizasyon_orani", "label": "Kapitalizasyon Oranı (%)", "type": "number"},
            {"key": "emsal_fiyat", "label": "Emsal Birim Fiyat (TL/m²)", "type": "number"},
        ],
    },
    {
        "id": "arsa",
        "name": "Arsa Değerleme Raporu",
        "description": "İmarlı veya imarsız arsa/arazi için değerleme raporu.",
        "icon": "Map",
        "cost_per_message": 3.0,
        "avg_report_cost": 20.0,
        "sections": [
            "Rapor Özeti",
            "Konum ve Ulaşım",
            "İmar Durumu",
            "Topografik Bilgiler",
            "Emsal Analiz",
            "Değer Tespiti",
        ],
        "fields": [
            {"key": "ada_parsel", "label": "Ada / Parsel No", "type": "text"},
            {"key": "il_ilce_mahalle", "label": "İl / İlçe / Mahalle", "type": "text"},
            {"key": "yuzolcumu", "label": "Yüzölçümü (m²)", "type": "number"},
            {"key": "imar_durumu", "label": "İmar Durumu (Konut/Ticari/Tarım)", "type": "text"},
            {"key": "kaks_taks", "label": "KAKS / TAKS", "type": "text"},
            {"key": "cephe_yol", "label": "Yola Cephe (m)", "type": "number"},
            {"key": "topografya", "label": "Topografya / Eğim", "type": "text"},
            {"key": "emsal_fiyat", "label": "Emsal Birim Fiyat (TL/m²)", "type": "number"},
        ],
    },
    {
        "id": "endustriyel",
        "name": "Endüstriyel Tesis Değerleme",
        "description": "Fabrika, depo veya lojistik tesis değerleme raporu.",
        "icon": "Factory",
        "cost_per_message": 8.0,
        "avg_report_cost": 55.0,
        "sections": [
            "Rapor Özeti",
            "Tesis Bilgileri",
            "Yapısal Analiz",
            "Kullanım Değeri ve Amortisman",
            "Piyasa Analizi",
            "Değer Tespiti",
        ],
        "fields": [
            {"key": "ada_parsel", "label": "Ada / Parsel No", "type": "text"},
            {"key": "adres", "label": "Açık Adres", "type": "textarea"},
            {"key": "arsa_alani", "label": "Arsa Alanı (m²)", "type": "number"},
            {"key": "kapali_alan", "label": "Kapalı Alan (m²)", "type": "number"},
            {"key": "yapi_tipi", "label": "Yapı Tipi (Çelik/Betonarme)", "type": "text"},
            {"key": "tavan_yuksekligi", "label": "Tavan Yüksekliği (m)", "type": "number"},
            {"key": "vinc_kapasitesi", "label": "Vinç / Yük Kapasitesi", "type": "text"},
            {"key": "elektrik_gucu", "label": "Bağlı Elektrik Gücü (kVA)", "type": "number"},
            {"key": "yas", "label": "Tesis Yaşı", "type": "number"},
            {"key": "emsal_fiyat", "label": "Emsal Birim Fiyat (TL/m²)", "type": "number"},
        ],
    },
]

FAQ_ITEMS = [
    # --- Yöntem & Yaklaşımlar ---
    {
        "category": "Yöntemler",
        "q": "Gayrimenkul değerlemede en yaygın kullanılan yöntemler nelerdir?",
        "a": "Üç ana yöntem kullanılır: (1) Emsal Karşılaştırma Yöntemi — benzer gayrimenkullerin satış fiyatları üzerinden değerleme, (2) Gelir Kapitalizasyonu Yöntemi — özellikle ticari mülkler için net kira gelirinin kapitalizasyon oranına bölünmesi, (3) Maliyet Yöntemi — yeniden yapım maliyeti + arsa değeri - amortisman. KırCan raporlarında en az iki yöntem uygulanır ve sonuç ağırlıklandırılır.",
    },
    {
        "category": "Yöntemler",
        "q": "Kapitalizasyon oranı (Cap Rate) nasıl hesaplanır?",
        "a": "Cap Rate = Net Yıllık İşletme Geliri (NOI) / Gayrimenkul Değeri. Örneğin yıllık 500.000 TL net kira geliri olan 10.000.000 TL değerindeki bir mülkün Cap Rate'i %5'tir. KırCan pratikte cap rate'i bölgesel karşılaştırılabilir işlemlerden ve Merkez Bankası tahvil getirilerine bindirilmiş risk primlerinden türetir.",
    },
    {
        "category": "Yöntemler",
        "q": "İndirgenmiş Nakit Akımı (DCF) yöntemi ne zaman tercih edilir?",
        "a": "Uzun kiralamalı ticari mülkler, otel, AVM, lojistik tesis ve geliştirme projelerinde DCF öne çıkar. En az 5-10 yıllık projeksiyon; TÜFE, doluluk oranı, işletme gider katsayısı ve terminal değer parametreleri kritik olur. KırCan varsayımları rapor sonunda ayrı bir 'Hassaslık Analizi' bölümünde açıklar.",
    },
    {
        "category": "Yöntemler",
        "q": "Maliyet yönteminde fonksiyonel eskime nasıl ölçülür?",
        "a": "Fonksiyonel eskime; modern ihtiyaca cevap veremeyen tasarım, teknoloji veya yerleşim planından kaynaklanır. Genellikle yeniden yapım maliyeti üzerinden %5–%25 arası bir kesinti olarak yansıtılır. KırCan; asansörsüz orta katlı binalar, düşük tavan yüksekliği veya ıslak hacim yetersizliği gibi somut delillerle bu oranı belgeler.",
    },
    {
        "category": "Yöntemler",
        "q": "Emsal seçiminde hangi kriterler dikkate alınır?",
        "a": "İdeal emsal; (1) son 6-12 ay içinde gerçekleşmiş, (2) konum, alan, imar ve yapı kalitesi bakımından benzer, (3) doğrulanabilir bir işlem olmalı. En az 3 emsal aranır; her emsale konum, tarih, alan, cephe, kat ve emsal düzeltmesi yapılır. KırCan raporlarında düzeltme tablosu şeffaf gösterilir.",
    },

    # --- Mevzuat & Standartlar ---
    {
        "category": "Mevzuat",
        "q": "SPK lisanslı değerleme raporu nedir ve kimler talep eder?",
        "a": "SPK (Sermaye Piyasası Kurulu) tarafından lisanslı değerleme şirketleri ve uzmanlarınca hazırlanan, gayrimenkul yatırım ortaklıkları, halka açık şirketler, bankalar (BDDK teminatları) ve mahkeme talepleri için kabul edilen resmi rapordur. KırCan SPK ve BDDK listelerinde yer alan uzman kadrosuyla hizmet verir.",
    },
    {
        "category": "Mevzuat",
        "q": "BDDK teminat değerleme raporunun özel gereklilikleri nelerdir?",
        "a": "BDDK raporları kredi teminatı amaçlıdır; likidasyon değeri, alım-satım karşılaştırması ve satılabilirlik süresi öne çıkar. Rapor formatı 2016/1 sayılı BDDK Yönetmeliğine uygun olmalı; imar durumu, tapu ekleri, fotoğraflar ve konum haritası zorunludur.",
    },
    {
        "category": "Mevzuat",
        "q": "Uluslararası Değerleme Standartları (IVS) neden önemlidir?",
        "a": "IVS; sınır ötesi yatırımcılar, çokuluslu şirketler ve UFRS (IFRS) finansal raporlaması için ortak dil sağlar. KırCan raporları IVS 2022 ile uyumlu olup 'Adil Piyasa Değeri' (Market Value) tanımını temel alır. Yerel mevzuatla uyumsuzluk durumunda her iki değer de sunulur.",
    },
    {
        "category": "Mevzuat",
        "q": "Değerleme raporunun geçerlilik süresi ne kadardır?",
        "a": "SPK raporları en fazla 6 ay, BDDK raporları çoğunlukla 3-6 ay geçerlidir. Piyasa koşullarında %10'un üzerinde ani değişim varsa geçerlilik daha kısa değerlendirilir. KırCan güncel piyasa hareketlerini takip ederek gerektiğinde 'kısa geçerlilikli rapor' notu düşer.",
    },

    # --- İmar & Hukuk ---
    {
        "category": "İmar & Hukuk",
        "q": "İmar durumu değerlemeyi nasıl etkiler?",
        "a": "İmar durumu KAKS (Emsal), TAKS, yükseklik ve kullanım amacını belirler; bu parametreler doğrudan yapılabilir alan miktarını ve dolayısıyla arsanın piyasa değerini belirler. İmar planındaki değişiklik beklentileri de 'imar beklenti primi' olarak değerlendirilebilir.",
    },
    {
        "category": "İmar & Hukuk",
        "q": "Tapu kaydında şerh, ipotek veya haciz varsa değer nasıl etkilenir?",
        "a": "Kısıtlayıcı şerhler (ipotek, haciz, satış vaadi, geçit hakkı, intifa vs.) mülkün alım-satım likiditesini ve dolayısıyla piyasa değerini düşürebilir. KırCan raporlarında bu şerhler ayrı bir bölümde listelenir; hangi şerhin değeri kaç TL etkilediği ayrıca belirtilir.",
    },
    {
        "category": "İmar & Hukuk",
        "q": "Kaçak yapı veya iskânsız binaların değerlemesinde nelere dikkat edilir?",
        "a": "İskânsız veya ruhsata aykırı yapılarda; yıkım riski, yasallaştırma maliyeti, elektrik/su aboneliği kısıtları ve satılabilirlik değeri düşürür. KırCan bu durumu 'İskân Yokluğu Düzeltmesi' olarak %10–%30 arası uygular ve alternatif değer senaryoları sunar.",
    },
    {
        "category": "İmar & Hukuk",
        "q": "Kat irtifakı ile kat mülkiyeti arasındaki fark değerlemede önemli midir?",
        "a": "Evet. Kat irtifakı tapusu inşaat aşamasındaki gayrimenkullerde verilir; kat mülkiyeti ise iskân alındıktan sonra oluşur. Kat mülkiyetli daireler bankalara daha rahat teminat olarak sunulabildiği için likidite avantajı sağlar; yaklaşık %3-%7 daha yüksek değerlenir.",
    },

    # --- Değer Kavramları ---
    {
        "category": "Değer Kavramları",
        "q": "Piyasa değeri, yatırım değeri ve tasfiye değeri arasındaki fark nedir?",
        "a": "**Piyasa değeri** (Market Value): açık piyasada makul sürede gerçekleşecek fiyat. **Yatırım değeri** (Investment Value): belirli bir yatırımcı için sağladığı fayda (subjektif). **Tasfiye değeri** (Liquidation Value): kısa sürede satış zorunluluğunda elde edilebilecek düşük değer. KırCan raporlarında hangi tanımın kullanıldığı ilk sayfada net belirtilir.",
    },
    {
        "category": "Değer Kavramları",
        "q": "Ekspertiz değeri ile piyasa değeri aynı şey midir?",
        "a": "Ekspertiz, bir uzmanın kanaatidir; piyasa değeri ise objektif kriterlerle desteklenen resmi tanımdır. Bankalar 'ekspertiz değeri' ifadesini kullansa da içerik olarak IVS piyasa değeri tanımı uygulanır. KırCan raporlarında her iki terim de eşdeğer kullanılır.",
    },

    # --- Uzmanlık Alanları ---
    {
        "category": "Uzmanlık",
        "q": "Otel değerlemesinde EBITDA çarpanları nasıl kullanılır?",
        "a": "Otellerde brüt oda geliri (RevPAR), doluluk oranı ve EBITDA marjı üzerinden değerleme yapılır. Türkiye'de 4-5 yıldızlı otellerde EBITDA çarpanı 8-12x aralığında; şehir/tatil, marka ve doluluk seviyesine göre değişir. KırCan otel uzmanları STR raporları ve rakip analizi kullanır.",
    },
    {
        "category": "Uzmanlık",
        "q": "Endüstriyel tesis değerlemesinde 'Highest and Best Use' analizi nasıl uygulanır?",
        "a": "Endüstriyel tesislerde mevcut kullanım optimum değilse alternatif senaryolar değerlendirilir: (a) mevcut fabrika olarak, (b) depo/lojistiğe dönüşüm, (c) arsa değeri olarak yeniden geliştirme. En yüksek net değeri sağlayan senaryo raporlanır. KırCan bu analizi 'HBU Karşılaştırma Tablosu' ile gösterir.",
    },
    {
        "category": "Uzmanlık",
        "q": "Tarım arazisi değerlemesinde hangi ek faktörler dikkate alınır?",
        "a": "Toprak sınıfı (I-VIII), sulama imkânı, drenaj, eğim, ana yollara mesafe, jeotermal/su kaynağı, imar geçiş beklentisi, tarımsal ürün paterni ve DSİ/sulama birliği aidatları belirleyicidir. Ayrıca 5403 sayılı Toprak Koruma Kanunu kapsamındaki kısıtlamalar rapor edilir.",
    },
    {
        "category": "Uzmanlık",
        "q": "Kültür varlığı tescilli binaların değerlemesinde özel yöntem var mıdır?",
        "a": "Tescilli yapılar için 2863 sayılı Kanun kısıtlamaları (grup 1/2), restorasyon zorunluluğu, kullanım sınırları ve devlet destekleri (vergi muafiyeti, restorasyon yardımı) hesaba katılır. KırCan bu tür raporlarda Koruma Kurulu kararlarını ek olarak sunar.",
    },

    # --- Süreç & Belgeler ---
    {
        "category": "Süreç",
        "q": "Değerleme raporu için hangi belgeler istenir?",
        "a": "Tapu senedi, imar durum belgesi, yapı ruhsatı, iskân belgesi (varsa), aplikasyon krokisi, kadastro paftası, projeler (kat planı, cephe), varsa kira sözleşmeleri, aidat/vergi belgeleri. Ticari mülklerde son 3 yıl kira gelirleri; sanayide üretim kapasitesi belgeleri de talep edilir.",
    },
    {
        "category": "Süreç",
        "q": "Yerinde inceleme (mahal ziyareti) zorunlu mudur?",
        "a": "SPK ve BDDK raporlarında mahal ziyareti ZORUNLUDUR; KırCan uzmanları GPS damgalı fotoğraf, çevre haritası, uydu görüntüsü ve komşu mülk incelemesi ile ziyareti belgeler. Ziyaret tarihi rapor kapağında yer alır ve değerin geçerlilik tarihidir.",
    },
    {
        "category": "Süreç",
        "q": "Uzaktan (masabaşı) değerleme geçerli midir?",
        "a": "Masabaşı ekspertiz (desktop appraisal) sadece indikatif değer üretir; resmi işlemlerde kullanılamaz. Ancak portföy önizleme veya erken durum tespiti için hızlı sonuç sağlar. KırCan bu tip çalışmalarda raporun 'Görüş Notu' olduğunu ilk sayfada bildirir.",
    },

    # --- Hesaplama Örnekleri ---
    {
        "category": "Hesaplama",
        "q": "Amortisman değerleme raporunda nasıl uygulanır?",
        "a": "Fiziksel yıpranma, fonksiyonel eskime ve dış etkenlere bağlı eskime olmak üzere üç bileşenden hesaplanır; toplam eskime yüzdesi yeniden yapım maliyetinden düşülerek net yapı değerine ulaşılır. Türkiye'de betonarme yapılarda yıllık %1-1.5 fiziksel amortisman kabul edilir (max ~50 yıl).",
    },
    {
        "category": "Hesaplama",
        "q": "Emsal düzeltmelerinde konum farkı nasıl sayısallaştırılır?",
        "a": "İki mikro-konum arası (aynı mahalle, farklı sokak) tipik olarak ±%5-%15 fiyat farkı üretir. KırCan; caddeye cephe, metro/toplu taşımaya mesafe, okul/park yakınlığı, gürültü/manzara gibi faktörleri ağırlıklandırarak matris ile düzeltme uygular ve emsal fiyatı 'ayarlanmış birim fiyat'a dönüştürür.",
    },
    {
        "category": "Hesaplama",
        "q": "Değerlemede KDV dahil mi hariç mi hesaplanır?",
        "a": "Piyasa değeri KDV HARİÇ olarak raporlanır. Konut satışlarında KDV %1/%10/%20 arasında değiştiği için, KDV dahil versiyon ayrı bir satır olarak gösterilir. Ticari gayrimenkullerde alıcının KDV'yi indirebiliyor olması alım kararını değiştirmez; piyasa değeri KDV hariç kalır.",
    },
]
