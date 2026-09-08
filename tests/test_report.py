import io
from datetime import date

import pytest

from amazon_vat_merger.report import (
    classify, parse_csv_date, read_report, to_float, transaction_from_row,
)

HEADER = (
    '"Marketplace ID","Merchant ID","Order Date","Transaction Type","Is Invoice Corrected","Order ID",'
    '"Shipment Date","Shipment ID","Transaction ID",ASIN,SKU,Quantity,"Tax Calculation Date","Tax Rate",'
    '"Product Tax Code",Currency,"Tax Type","Tax Calculation Reason Code","Tax Reporting Scheme",'
    '"Tax Collection Responsibility","Tax Address Role","Jurisdiction Level","Jurisdiction Name",'
    '"OUR_PRICE Tax Inclusive Selling Price","OUR_PRICE Tax Amount","OUR_PRICE Tax Exclusive Selling Price",'
    '"OUR_PRICE Tax Inclusive Promo Amount","OUR_PRICE Tax Amount Promo","OUR_PRICE Tax Exclusive Promo Amount",'
    '"SHIPPING Tax Inclusive Selling Price","SHIPPING Tax Amount","SHIPPING Tax Exclusive Selling Price",'
    '"SHIPPING Tax Inclusive Promo Amount","SHIPPING Tax Amount Promo","SHIPPING Tax Exclusive Promo Amount",'
    '"GIFTWRAP Tax Inclusive Selling Price","GIFTWRAP Tax Amount","GIFTWRAP Tax Exclusive Selling Price",'
    '"GIFTWRAP Tax Inclusive Promo Amount","GIFTWRAP Tax Amount Promo","GIFTWRAP Tax Exclusive Promo Amount",'
    '"Seller Tax Registration","Seller Tax Registration Jurisdiction","Buyer Tax Registration",'
    '"Buyer Tax Registration Jurisdiction","Buyer Tax Registration Type","Buyer E Invoice Account Id",'
    '"Invoice Level Currency Code","Invoice Level Exchange Rate","Invoice Level Exchange Rate Date",'
    '"Converted Tax Amount","VAT Invoice Number","Invoice Url","Export Outside EU","Ship From City",'
    '"Ship From State","Ship From Country","Ship From Postal Code","Ship From Tax Location Code","Ship To City",'
    '"Ship To State","Ship To Country","Ship To Postal Code","Ship To Location Code","Return Fc Country",'
    '"Is Amazon Invoiced","Original VAT Invoice Number","Invoice Correction Details","E-Invoice Delivery Status",'
    '"E-Invoice Error Code","E-Invoice Error Description","E-Invoice Status Last Updated Date","EInvoice URL",'
    '"Buyer Peppol Id","Seller Peppol Id","Buyer NIP","Seller NIP","KSeF Number","Seller SIREN","Buyer SIREN",'
    '"Seller SIRET","Buyer SIRET","Seller Routing Code","Buyer Routing Code"'
)

# wiersz z promocją na wysyłkę (3,99 – 3,99 = 0) – dane syntetyczne
ROW_OSS = (
    'DE,1,"28-Aug-2026 UTC",SHIPMENT,FALSE,111-1111111-1111111,"29-Aug-2026 UTC",1,1,B000000001,sku1,1,'
    '"28-Aug-2026 UTC",0.1900,A_GEN_STANDARD,EUR,VAT,Taxable,VCS_EU_OSS,Seller,ShipTo,Country,GERMANY,'
    '27.50,4.39,23.11,0.00,0.00,0.00,3.99,0.64,3.35,-3.99,-0.64,-3.35,0.00,0.00,0.00,0.00,0.00,0.00,'
    'PL0000000000,PL,,,,,,0.0000,,0.00,PL6000000000AA,"https://x/1",false,Sady,,PL,62-080,1,Berlin,,DE,10115,1,,true,'
    ',,,,,,,,,,,,,,,,,,'
)
ROW_WDT = (
    'PL,1,"28-Aug-2026 UTC",SHIPMENT,FALSE,222-2222222-2222222,"29-Aug-2026 UTC",2,2,B000000002,sku2,2,'
    '"28-Aug-2026 UTC",0.0000,A_GEN_STANDARD,PLN,VAT,Taxable,,Seller,ShipFrom,Country,"CZECH REPUBLIC",'
    '121.87,0.00,121.87,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,'
    'CZ000000000,CZ,PL0000000001,PL,VAT,,CZK,5.5685,"27-Aug-2026 UTC",0.00,CZ6000000000AA,"https://x/2",false,Kojetin,,CZ,"752 01",1,Rzeszów,,PL,35-205,1,,true,'
    ',,,,,,,,,,,,,,,,,,'
)
ROW_REFUND_GB = (
    'GB,1,"12-Aug-2026 UTC",REFUND,FALSE,333-3333333-3333333,"29-Aug-2026 UTC",3,"amzn1:crow:x",B000000003,sku3,1,'
    '"12-Aug-2026 UTC",0.0000,A_GEN_STANDARD,GBP,VAT,Taxable,DEEMED_RESELLER,Marketplace,ShipFrom,Country,FRANCE,'
    '-29.08,0.00,-29.08,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,'
    'FR00000000000,FR,,,,,,0.0000,,0.00,FR6000000000AR,"https://x/3",true,Brebieres,,FR,62117,1,LEEDS,,GB,"LS1 1AA",1,,true,'
    ',,,,,,,,,,,,,,,,,,'
)
ROW_LOCAL_B2B = (
    'DE,1,"26-Aug-2026 UTC",SHIPMENT,FALSE,444-4444444-4444444,"29-Aug-2026 UTC",4,4,B000000004,sku4,1,'
    '"29-Aug-2026 UTC",0.1900,A_GEN_STANDARD,EUR,VAT,Taxable,,Seller,ShipTo,Country,GERMANY,'
    '28.89,4.61,24.28,0.00,0.00,0.00,2.00,0.32,1.68,-2.00,-0.32,-1.68,0.00,0.00,0.00,0.00,0.00,0.00,'
    'DE000000000,DE,DE000000001,DE,VAT,,,0.0000,,0.00,DE6000000000AA,"https://x/4",false,Soest,,DE,59494,1,Soest,,DE,59494,1,,true,'
    ',,,,,,,,,,,,,,,,,,'
)


def _write(tmp_path, *rows):
    p = tmp_path / "r.csv"
    p.write_text("﻿" + HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def test_parse_csv_date():
    assert parse_csv_date("12-Aug-2026 UTC") == date(2026, 8, 12)
    assert parse_csv_date("2026-08-12") == date(2026, 8, 12)
    assert parse_csv_date("") is None
    assert parse_csv_date("05-Sep-2026") == date(2026, 9, 5)


def test_to_float():
    assert to_float("-29.08") == -29.08
    assert to_float("1.234,56") == 1234.56
    assert to_float("1,234.56") == 1234.56
    assert to_float("") is None


def test_amounts_with_promo_and_categories(tmp_path):
    txs = read_report(_write(tmp_path, ROW_OSS, ROW_WDT, ROW_REFUND_GB, ROW_LOCAL_B2B))
    assert len(txs) == 4
    oss, wdt, ref, b2b = txs
    # promocja na wysyłkę znosi koszt wysyłki
    assert oss.total.net == 23.11 and oss.total.vat == 4.39 and oss.total.gross == 27.50
    assert oss.shipping.net == 0.0 and oss.shipping.gross == 0.0
    assert oss.category == "OSS" and oss.tab_name == "DE OSS"
    assert oss.tax_rate_pct == 19.0
    assert oss.order_date == date(2026, 8, 28) and oss.shipment_date == date(2026, 8, 29)

    assert wdt.category == "WDT" and wdt.tab_name == "CZ WDT"
    assert wdt.invoice_currency == "CZK" and wdt.invoice_exchange_rate == 5.5685
    assert wdt.quantity == 2

    assert ref.category == "Marketplace" and ref.tab_name == "FR Marketplace KOREKTA"
    assert ref.total.gross == -29.08 and ref.is_negative
    assert ref.transaction_type_pl == "Zwrot płatności"

    assert b2b.category == "B2B" and b2b.tab_name == "DE B2B"
    assert b2b.total.net == 24.28 and b2b.total.vat == 4.61


def test_missing_columns_raises(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_report(p)


def test_classify_export():
    tx = transaction_from_row({"Export Outside EU": "true", "Ship To Country": "CH", "Ship From Country": "DE",
                               "Seller Tax Registration Jurisdiction": "DE", "Tax Rate": "0"})
    assert tx.category == "Eksport" and tx.tab_name == "DE Eksport"
