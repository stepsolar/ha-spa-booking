<?php
/**
 * «Stile shop»: shop and product page restyled in the site's own template
 * style. Off by default; switched on in WooCommerce › Spa Booking. Switching
 * it off puts the pages back exactly as they were (nothing is stored in the
 * theme or in the products, apart from the optional per-product texts).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class Spa_Booking_Shop_Style {
	const META_INFO  = '_sbc_card_info';
	const META_FACTS = '_sbc_facts';
	const META_NOTE  = '_sbc_note';

	public static function defaults() {
		return array(
			'style_on'       => 0,
			'style_title'    => 'Acquista la tua esperienza di benessere',
			'style_subtitle' => 'Ricevi subito il voucher via email · acconto 50% se è per te, intero se è un regalo',
			'style_tabs'     => "ingresso-spa|Ingresso Spa\nmassaggi|Massaggi\nrituali-romantici|Rituali di coppia\nday-spa|Day Spa\nprivate-jacuzzi|Private Jacuzzi\ngift-card|Gift Card\nofferta|Offerte",
			'style_note'     => '',
			'style_trust'    => "Voucher subito via email\nPagamento sicuro",
			'style_from'     => 1,
		);
	}

	public static function sanitize( $in ) {
		return array(
			'style_on'       => empty( $in['style_on'] ) ? 0 : 1,
			'style_title'    => sanitize_text_field( $in['style_title'] ?? '' ),
			'style_subtitle' => sanitize_text_field( $in['style_subtitle'] ?? '' ),
			'style_tabs'     => sanitize_textarea_field( $in['style_tabs'] ?? '' ),
			'style_note'     => sanitize_text_field( $in['style_note'] ?? '' ),
			'style_trust'    => sanitize_textarea_field( $in['style_trust'] ?? '' ),
			'style_from'     => empty( $in['style_from'] ) ? 0 : 1,
		);
	}

	private static function o( $key ) {
		$o = Spa_Booking_Connector::options();
		return $o[ $key ] ?? '';
	}

	private static function lines( $text ) {
		return array_values( array_filter( array_map( 'trim', preg_split( '/\r?\n/', (string) $text ) ) ) );
	}

	public static function init() {
		// The per-product texts can be written even while the style is off.
		add_action( 'woocommerce_product_options_general_product_data', array( __CLASS__, 'product_fields' ) );
		add_action( 'woocommerce_admin_process_product_object', array( __CLASS__, 'save_product_fields' ) );
		if ( is_admin() || ! self::o( 'style_on' ) ) {
			return;
		}
		add_filter( 'body_class', array( __CLASS__, 'body_class' ) );
		add_action( 'wp_enqueue_scripts', array( __CLASS__, 'assets' ), 99 );
		// Shop and category pages.
		add_action( 'woocommerce_archive_description', array( __CLASS__, 'head' ), 20 );
		add_action( 'woocommerce_before_shop_loop', array( __CLASS__, 'tabs' ), 5 );
		add_action( 'woocommerce_shop_loop_item_title', array( __CLASS__, 'kind' ), 5 );
		add_action( 'woocommerce_after_shop_loop_item_title', array( __CLASS__, 'card_info' ), 5 );
		add_filter( 'woocommerce_get_price_html', array( __CLASS__, 'price_from' ), 20, 2 );
		// Product page.
		add_action( 'woocommerce_before_single_product', array( __CLASS__, 'breadcrumb' ), 5 );
		add_action( 'woocommerce_single_product_summary', array( __CLASS__, 'kind_single' ), 4 );
		add_action( 'woocommerce_single_product_summary', array( __CLASS__, 'facts' ), 25 );
		add_action( 'woocommerce_single_product_summary', array( __CLASS__, 'trust' ), 32 );
	}

	public static function body_class( $classes ) {
		if ( function_exists( 'is_woocommerce' ) && ( is_woocommerce() || is_cart() ) ) {
			$classes[] = 'sbc-style';
		}
		return $classes;
	}

	public static function assets() {
		if ( ! function_exists( 'is_woocommerce' ) || ! ( is_woocommerce() || is_cart() ) ) {
			return;
		}
		$base = plugin_dir_url( __FILE__ ) . 'assets/';
		wp_enqueue_style( 'sbc-shop-style', $base . 'shop-style.css', array(), Spa_Booking_Connector::VERSION );
		if ( is_product() ) {
			wp_enqueue_script( 'sbc-shop-style', $base . 'shop-style.js', array( 'jquery' ), Spa_Booking_Connector::VERSION, true );
		}
	}

	/* ---------------------------------------------------------------- shop */

	private static function is_shop_root() {
		return function_exists( 'is_shop' ) && is_shop() && ! is_search();
	}

	/**
	 * The heading above the tabs. The theme hides WooCommerce's own h1 (and
	 * shows the shop page's text instead), so the style prints its own:
	 * the configured title and subtitle on the shop, the name on a category.
	 */
	public static function head() {
		if ( self::is_shop_root() ) {
			$title = self::o( 'style_title' );
			$sub   = self::o( 'style_subtitle' );
		} elseif ( is_product_category() ) {
			$title = single_term_title( '', false );
			$sub   = '';
		} else {
			return;
		}
		if ( '' === $title && '' === $sub ) {
			return;
		}
		echo '<div class="sbc-head">';
		if ( '' !== $title ) {
			echo '<h2 class="sbc-title">' . esc_html( $title ) . '</h2>';
		}
		if ( '' !== $sub ) {
			echo '<p class="sbc-subtitle">' . esc_html( $sub ) . '</p>';
		}
		echo '</div>';
	}

	/** «slug|Etichetta» lines → [slug => label], only categories that exist. */
	private static function tab_list() {
		$out = array();
		foreach ( self::lines( self::o( 'style_tabs' ) ) as $line ) {
			$parts = array_map( 'trim', explode( '|', $line, 2 ) );
			$term  = get_term_by( 'slug', sanitize_title( $parts[0] ), 'product_cat' );
			if ( $term && ! is_wp_error( $term ) ) {
				$out[ $term->slug ] = array( $term, '' !== ( $parts[1] ?? '' ) ? $parts[1] : $term->name );
			}
		}
		return $out;
	}

	public static function tabs() {
		if ( ! ( self::is_shop_root() || is_product_category() ) ) {
			return;
		}
		$tabs = self::tab_list();
		if ( ! $tabs ) {
			return;
		}
		$current = is_product_category() ? get_queried_object() : null;
		echo '<nav class="sbc-cats" aria-label="Categorie">';
		printf( '<a href="%s"%s>%s</a>', esc_url( wc_get_page_permalink( 'shop' ) ), $current ? '' : ' class="on" aria-current="page"', esc_html__( 'Tutti', 'spa-booking-connector' ) );
		foreach ( $tabs as $slug => $tab ) {
			$on = $current && $current->slug === $slug;
			printf( '<a href="%s"%s>%s</a>', esc_url( get_term_link( $tab[0] ) ), $on ? ' class="on" aria-current="page"' : '', esc_html( $tab[1] ) );
		}
		echo '</nav>';
	}

	/** The product's kind: its first category among the tabs, else its first category. */
	private static function kind_label( $product ) {
		$ids = $product->get_category_ids();
		foreach ( self::tab_list() as $tab ) {
			if ( in_array( $tab[0]->term_id, $ids, true ) ) {
				return $tab[1];
			}
		}
		$term = $ids ? get_term( $ids[0], 'product_cat' ) : null;
		return ( $term && ! is_wp_error( $term ) ) ? html_entity_decode( $term->name ) : '';
	}

	public static function kind() {
		global $product;
		if ( $product ) {
			$label = self::kind_label( $product );
			if ( '' !== $label ) {
				echo '<span class="sbc-kind">' . esc_html( $label ) . '</span>';
			}
		}
	}

	public static function card_info() {
		global $product;
		$info = $product ? trim( (string) $product->get_meta( self::META_INFO ) ) : '';
		if ( '' !== $info ) {
			echo '<span class="sbc-info">' . esc_html( $info ) . '</span>';
		}
	}

	/** Variable products: «da 80,00 €» instead of «80,00 € – 100,00 €». */
	public static function price_from( $html, $product ) {
		if ( ! self::o( 'style_from' ) || ! $product || ! $product->is_type( 'variable' ) ) {
			return $html;
		}
		$min = $product->get_variation_price( 'min', true );
		$max = $product->get_variation_price( 'max', true );
		if ( '' === $min || $min === $max ) {
			return $html;
		}
		return '<small class="sbc-from">' . esc_html__( 'da', 'spa-booking-connector' ) . '</small> ' . wc_price( $min );
	}

	/* ------------------------------------------------------------- product */

	public static function breadcrumb() {
		if ( function_exists( 'woocommerce_breadcrumb' ) ) {
			woocommerce_breadcrumb( array( 'wrap_before' => '<nav class="woocommerce-breadcrumb sbc-crumb">', 'delimiter' => ' / ' ) );
		}
	}

	public static function kind_single() {
		global $product;
		if ( $product ) {
			$names = array();
			$tabs  = self::tab_list();
			foreach ( $tabs as $tab ) {
				if ( in_array( $tab[0]->term_id, $product->get_category_ids(), true ) ) {
					$names[] = $tab[1];
				}
			}
			if ( ! $names ) {
				$names[] = self::kind_label( $product );
			}
			$names = array_filter( $names );
			if ( $names ) {
				echo '<div class="sbc-kind">' . esc_html( implode( ' · ', $names ) ) . '</div>';
			}
		}
	}

	public static function facts() {
		global $product;
		if ( ! $product ) {
			return;
		}
		$facts = self::lines( $product->get_meta( self::META_FACTS ) );
		if ( $facts ) {
			echo '<ul class="sbc-facts">';
			foreach ( $facts as $fact ) {
				echo '<li>' . esc_html( $fact ) . '</li>';
			}
			echo '</ul>';
		}
		$note = trim( (string) $product->get_meta( self::META_NOTE ) );
		if ( '' === $note ) {
			$note = self::o( 'style_note' );
		}
		if ( '' !== $note ) {
			echo '<p class="sbc-note">' . esc_html( $note ) . '</p>';
		}
	}

	public static function trust() {
		$lines = self::lines( self::o( 'style_trust' ) );
		if ( $lines ) {
			echo '<ul class="sbc-trust">';
			foreach ( $lines as $line ) {
				echo '<li>' . esc_html( $line ) . '</li>';
			}
			echo '</ul>';
		}
	}

	/* --------------------------------------------------------------- admin */

	public static function product_fields() {
		echo '<div class="options_group">';
		woocommerce_wp_text_input( array(
			'id'          => self::META_INFO,
			'label'       => 'Riga nello shop',
			'placeholder' => '2 persone · 2 ore',
			'desc_tip'    => true,
			'description' => 'Spa Booking › Stile shop: riga breve sotto il nome, nella lista dello shop.',
		) );
		woocommerce_wp_textarea_input( array(
			'id'          => self::META_FACTS,
			'label'       => 'In breve',
			'placeholder' => "2 ore\n2 persone\nTelo piscina incluso",
			'desc_tip'    => true,
			'description' => 'Una voce per riga: compaiono sotto la descrizione breve, tra due linee sottili.',
		) );
		woocommerce_wp_text_input( array(
			'id'          => self::META_NOTE,
			'label'       => 'Nota sotto il prezzo',
			'placeholder' => 'Prenotazione obbligatoria. Dal martedì alla domenica.',
			'desc_tip'    => true,
			'description' => 'Vuota = la nota generale di WooCommerce › Spa Booking.',
		) );
		echo '</div>';
	}

	public static function save_product_fields( $product ) {
		// phpcs:disable WordPress.Security.NonceVerification -- WooCommerce checks the product form nonce.
		if ( isset( $_POST[ self::META_INFO ] ) ) {
			$product->update_meta_data( self::META_INFO, sanitize_text_field( wp_unslash( $_POST[ self::META_INFO ] ) ) );
		}
		if ( isset( $_POST[ self::META_FACTS ] ) ) {
			$product->update_meta_data( self::META_FACTS, sanitize_textarea_field( wp_unslash( $_POST[ self::META_FACTS ] ) ) );
		}
		if ( isset( $_POST[ self::META_NOTE ] ) ) {
			$product->update_meta_data( self::META_NOTE, sanitize_text_field( wp_unslash( $_POST[ self::META_NOTE ] ) ) );
		}
		// phpcs:enable
	}

	/** The settings rows, printed inside the connector's settings table. */
	public static function settings_rows( $o ) {
		$n = Spa_Booking_Connector::OPTION;
		?>
		<tr><th colspan="2"><h2 style="margin:10px 0 0">Stile shop</h2></th></tr>
		<tr><th>Nuovo stile</th><td><label><input type="checkbox" name="<?php echo esc_attr( $n ); ?>[style_on]" value="1" <?php checked( $o['style_on'] ); ?>> Attivo su shop, categorie e schede prodotto</label><p class="description">Togliendo la spunta le pagine tornano esattamente come prima.</p></td></tr>
		<tr><th>Titolo dello shop</th><td><input type="text" class="large-text" name="<?php echo esc_attr( $n ); ?>[style_title]" value="<?php echo esc_attr( $o['style_title'] ); ?>"></td></tr>
		<tr><th>Sottotitolo</th><td><input type="text" class="large-text" name="<?php echo esc_attr( $n ); ?>[style_subtitle]" value="<?php echo esc_attr( $o['style_subtitle'] ); ?>"></td></tr>
		<tr><th>Categorie in alto</th><td><textarea class="large-text code" rows="7" name="<?php echo esc_attr( $n ); ?>[style_tabs]"><?php echo esc_textarea( $o['style_tabs'] ); ?></textarea><p class="description">Una per riga: <code>slug-categoria|Etichetta</code> (l'etichetta è facoltativa). Le categorie che non esistono sono saltate.</p></td></tr>
		<tr><th>Prezzi «da»</th><td><label><input type="checkbox" name="<?php echo esc_attr( $n ); ?>[style_from]" value="1" <?php checked( $o['style_from'] ); ?>> Per i prodotti con varianti mostra «da 80,00 €» invece di «80,00 € – 100,00 €»</label></td></tr>
		<tr><th>Nota sotto il prezzo</th><td><input type="text" class="large-text" name="<?php echo esc_attr( $n ); ?>[style_note]" value="<?php echo esc_attr( $o['style_note'] ); ?>" placeholder="Prenotazione obbligatoria. Dal martedì alla domenica, ponti e festività esclusi."><p class="description">Per tutti i prodotti; ogni prodotto può averne una sua (Dati prodotto › Generale).</p></td></tr>
		<tr><th>Rassicurazioni</th><td><textarea class="large-text" rows="3" name="<?php echo esc_attr( $n ); ?>[style_trust]"><?php echo esc_textarea( $o['style_trust'] ); ?></textarea><p class="description">Una per riga, sotto il pulsante del carrello.</p></td></tr>
		<?php
	}
}

Spa_Booking_Shop_Style::init();
