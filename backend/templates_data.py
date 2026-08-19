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
    {
        "q": "Gayrimenkul değerlemede en yaygın kullanılan yöntemler nelerdir?",
        "a": "Üç ana yöntem kullanılır: (1) Emsal Karşılaştırma Yöntemi — benzer gayrimenkullerin satış fiyatları üzerinden değerleme, (2) Gelir Kapitalizasyonu Yöntemi — özellikle ticari mülkler için net kira gelirinin kapitalizasyon oranına bölünmesi, (3) Maliyet Yöntemi — yeniden yapım maliyeti + arsa değeri - amortisman.",
    },
    {
        "q": "SPK lisanslı değerleme raporu nedir?",
        "a": "SPK (Sermaye Piyasası Kurulu) tarafından lisanslı değerleme şirketleri ve uzmanlarınca hazırlanan, gayrimenkul yatırım ortaklıkları, bankalar ve halka açık şirketlerin işlemlerinde kabul edilen resmi raporlardır.",
    },
    {
        "q": "Kapitalizasyon oranı (Cap Rate) nasıl hesaplanır?",
        "a": "Cap Rate = Net Yıllık İşletme Geliri (NOI) / Gayrimenkul Değeri. Örneğin yıllık 500.000 TL net kira geliri olan 10.000.000 TL değerindeki bir mülkün Cap Rate'i %5'tir.",
    },
    {
        "q": "İmar durumu değerlemeyi nasıl etkiler?",
        "a": "İmar durumu KAKS (Emsal), TAKS, yükseklik ve kullanım amacını belirler; bu parametreler doğrudan yapılabilir alan miktarını ve dolayısıyla arsanın piyasa değerini belirler.",
    },
    {
        "q": "Amortisman değerleme raporunda nasıl uygulanır?",
        "a": "Fiziksel yıpranma, fonksiyonel eskime ve dış etkenlere bağlı eskime olmak üzere üç bileşenden hesaplanır; toplam eskime yüzdesi yeniden yapım maliyetinden düşülerek net yapı değerine ulaşılır.",
    },
]
