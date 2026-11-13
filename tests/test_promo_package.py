"""2.8.5: a promo can offer a package of the online shop."""

from __future__ import annotations

from custom_components.spa_booking.normalize import _norm_settings


def test_promo_text_names_the_package_with_price_and_link(coordinator) -> None:
    settings = coordinator._data["settings"]
    settings.update(_norm_settings({**settings, "wp_url": "spa.example.it", "wp_products": [
        {"product_id": 41, "variation_id": 0, "name": "You&Me Relax", "price": 120,
         "url": "https://spa.example.it/prodotto/you-me/"},
        {"product_id": 52, "variation_id": 0, "name": "Gift card 50", "price": 50},
    ]}))
    promo = {"message": "Ciao {nome}! {pacchetto} a {prezzo_pacchetto} invece di {prezzo_listino}: {link_pacchetto}",
             "product_key": "41:0", "product_promo_price": 99}
    text = coordinator.format_promo({"first_name": "Anna"}, promo=promo)
    assert text == "Ciao Anna! You&Me Relax a 99,00 € invece di 120,00 €: https://spa.example.it/prodotto/you-me/"
    # An old plugin without the page link: the WordPress product address.
    other = coordinator.format_promo({"first_name": "Anna"}, promo={"message": "{link_pacchetto}", "product_key": "52:0"})
    assert other == "https://spa.example.it/?post_type=product&p=52"
    # A product gone from the shop: the snapshot saved with the promo.
    gone = coordinator.format_promo({}, promo={"message": "{pacchetto} {prezzo_pacchetto}", "product_key": "9:0",
                                              "product_name": "Natale di coppia", "product_price": 150})
    assert gone == "Natale di coppia 150,00 €"
