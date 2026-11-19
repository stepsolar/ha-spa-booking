<?php
/**
 * Plugin Name: Spa Booking Connector
 * Description: Collega il sito a Spa Booking: voucher venduti con «Buoni PDF» (riscattati in spa), iscritti alla newsletter, clienti dello shop, codici sconto della newsletter, gift card di Spa Booking usabili nello shop, modifica dei prodotti e ordini dello shop, stile dello shop e delle schede prodotto.
 * Version: 1.8.0
 * Author: Spa Booking
 * Requires PHP: 7.4
 * Text Domain: spa-booking-connector
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class Spa_Booking_Connector {
	const VERSION   = '1.8.0';
	const OPTION    = 'spa_booking_connector';
	const NAMESPACE = 'spa-booking/v1';

	public static function init() {
		add_action( 'rest_api_init', array( __CLASS__, 'routes' ) );
		add_action( 'admin_menu', array( __CLASS__, 'menu' ) );
		add_action( 'admin_init', array( __CLASS__, 'register_settings' ) );
		// A paid order: tell Spa Booking straight away (it also checks every 15 minutes).
		add_action( 'woocommerce_order_status_processing', array( __CLASS__, 'notify' ), 99 );
		add_action( 'woocommerce_order_status_completed', array( __CLASS__, 'notify' ), 99 );
		add_action( 'woocommerce_order_status_refunded', array( __CLASS__, 'notify' ), 99 );
		add_action( 'woocommerce_order_status_cancelled', array( __CLASS__, 'notify' ), 99 );
		// 1.8.0: a Spa Booking gift card spent in an order (or given back).
		add_action( 'woocommerce_order_status_processing', array( __CLASS__, 'gift_used' ), 98 );
		add_action( 'woocommerce_order_status_completed', array( __CLASS__, 'gift_used' ), 98 );
		add_action( 'woocommerce_order_status_cancelled', array( __CLASS__, 'gift_back' ), 98 );
		add_action( 'woocommerce_order_status_refunded', array( __CLASS__, 'gift_back' ), 98 );
		add_action( 'woocommerce_order_status_failed', array( __CLASS__, 'gift_back' ), 98 );
	}

	/* ------------------------------------------------------------ settings */

	public static function options() {
		$o = get_option( self::OPTION, array() );
		return wp_parse_args( is_array( $o ) ? $o : array(), array_merge( array( 'secret' => '', 'notify_url' => '', 'redeem_user' => 0 ), Spa_Booking_Shop_Style::defaults() ) );
	}

	public static function register_settings() {
		register_setting( 'spa_booking_connector', self::OPTION, array(
			'type'              => 'array',
			'sanitize_callback' => function ( $in ) {
				return array_merge( array(
					'secret'      => sanitize_text_field( $in['secret'] ?? '' ),
					'notify_url'  => esc_url_raw( trim( $in['notify_url'] ?? '' ) ),
					'redeem_user' => absint( $in['redeem_user'] ?? 0 ),
				), Spa_Booking_Shop_Style::sanitize( is_array( $in ) ? $in : array() ) );
			},
		) );
	}

	public static function menu() {
		add_submenu_page( 'woocommerce', 'Spa Booking', 'Spa Booking', 'manage_woocommerce', 'spa-booking-connector', array( __CLASS__, 'page' ) );
	}

	public static function page() {
		$o = self::options();
		?>
		<div class="wrap">
			<h1>Spa Booking Connector</h1>
			<p>Copia qui la <b>chiave</b> e l'<b>indirizzo di notifica</b> che trovi in Spa Booking › Configurazione › Shop online.</p>
			<form method="post" action="options.php">
				<?php settings_fields( 'spa_booking_connector' ); ?>
				<table class="form-table">
					<tr><th>Chiave segreta</th><td><input type="text" class="regular-text code" name="<?php echo esc_attr( self::OPTION ); ?>[secret]" value="<?php echo esc_attr( $o['secret'] ); ?>" autocomplete="off"></td></tr>
					<tr><th>Indirizzo di notifica</th><td><input type="url" class="large-text code" name="<?php echo esc_attr( self::OPTION ); ?>[notify_url]" value="<?php echo esc_attr( $o['notify_url'] ); ?>" placeholder="https://.../api/spa_booking/wp/notify"><p class="description">Facoltativo: senza, Spa Booking controlla gli ordini ogni 15 minuti.</p></td></tr>
					<tr><th>Utente che riscatta</th><td><?php wp_dropdown_users( array( 'name' => self::OPTION . '[redeem_user]', 'selected' => $o['redeem_user'], 'role__in' => array( 'administrator', 'shop_manager' ), 'show_option_none' => '— utente attuale —', 'option_none_value' => 0 ) ); ?><p class="description">Compare come «riscattato da» nei Buoni PDF.</p></td></tr>
					<?php Spa_Booking_Shop_Style::settings_rows( $o ); ?>
				</table>
				<?php submit_button(); ?>
			</form>
			<p>Buoni PDF: <?php echo self::vou_active() ? '<b style="color:#1a7f37">attivo</b>' : '<b style="color:#b32d2e">non trovato</b>'; ?> · versione connettore <?php echo esc_html( self::VERSION ); ?></p>
		</div>
		<?php
	}

	/* ---------------------------------------------------------------- REST */

	public static function routes() {
		$auth = array( __CLASS__, 'allowed' );
		register_rest_route( self::NAMESPACE, '/status', array( 'methods' => 'GET', 'callback' => array( __CLASS__, 'status' ), 'permission_callback' => $auth ) );
		register_rest_route( self::NAMESPACE, '/products', array( 'methods' => 'GET', 'callback' => array( __CLASS__, 'products' ), 'permission_callback' => $auth ) );
		// 1.3.0: one product to read and change, and the shop's categories.
		register_rest_route( self::NAMESPACE, '/product', array(
			array( 'methods' => 'GET', 'callback' => array( __CLASS__, 'product' ), 'permission_callback' => $auth ),
			array( 'methods' => 'POST', 'callback' => array( __CLASS__, 'product_update' ), 'permission_callback' => $auth ),
		) );
		// 1.4.0: the shop's orders.
		register_rest_route( self::NAMESPACE, '/orders', array( 'methods' => 'GET', 'callback' => array( __CLASS__, 'orders' ), 'permission_callback' => $auth ) );
		register_rest_route( self::NAMESPACE, '/order', array(
			array( 'methods' => 'GET', 'callback' => array( __CLASS__, 'order' ), 'permission_callback' => $auth ),
			array( 'methods' => 'POST', 'callback' => array( __CLASS__, 'order_update' ), 'permission_callback' => $auth ),
		) );
		register_rest_route( self::NAMESPACE, '/vouchers', array( 'methods' => 'GET', 'callback' => array( __CLASS__, 'vouchers' ), 'permission_callback' => $auth ) );
		register_rest_route( self::NAMESPACE, '/redeem', array( 'methods' => 'POST', 'callback' => array( __CLASS__, 'redeem' ), 'permission_callback' => $auth ) );
		// 1.2.0: the people of the site and the newsletter discount codes.
		register_rest_route( self::NAMESPACE, '/contacts', array( 'methods' => 'GET', 'callback' => array( __CLASS__, 'contacts' ), 'permission_callback' => $auth ) );
		register_rest_route( self::NAMESPACE, '/coupon-use', array( 'methods' => 'POST', 'callback' => array( __CLASS__, 'coupon_use' ), 'permission_callback' => $auth ) );
		// 1.7.0: a new expiry date for a code, expired or not.
		register_rest_route( self::NAMESPACE, '/voucher-expiry', array( 'methods' => 'POST', 'callback' => array( __CLASS__, 'voucher_expiry' ), 'permission_callback' => $auth ) );
		register_rest_route( self::NAMESPACE, '/gift-cards', array( 'methods' => 'POST', 'callback' => array( __CLASS__, 'gift_cards' ), 'permission_callback' => $auth ) );
		register_rest_route( self::NAMESPACE, '/diag', array( 'methods' => 'GET', 'callback' => array( __CLASS__, 'diag' ), 'permission_callback' => $auth ) );
	}

	/** The shared key from Spa Booking, or a shop manager signed in. */
	public static function allowed( WP_REST_Request $request ) {
		$secret = self::options()['secret'];
		$given  = (string) $request->get_header( 'x-spa-booking-key' );
		if ( '' !== $secret && '' !== $given && hash_equals( $secret, $given ) ) {
			return true;
		}
		return current_user_can( 'manage_woocommerce' );
	}

	public static function status() {
		return array(
			'ok'          => true,
			'version'     => self::VERSION,
			'woocommerce' => class_exists( 'WooCommerce' ),
			'buoni_pdf'   => self::vou_active(),
			'newsletter'  => self::newsletter_table() !== '',
			'site'        => get_bloginfo( 'name' ),
		);
	}

	/** Every product and variation, to pair with the treatments. */
	public static function products() {
		$out = array();
		// 1.4.0: drafts and products waiting for review too, to publish them from Spa Booking.
		$ids = wc_get_products( array( 'status' => array( 'publish', 'private', 'draft', 'pending' ), 'limit' => 500, 'return' => 'ids' ) );
		foreach ( $ids as $id ) {
			$p = wc_get_product( $id );
			if ( ! $p ) {
				continue;
			}
			// 1.1.0: page and picture, so Spa Booking can link a package in a promo.
			$image = $p->get_image_id() ? wp_get_attachment_image_url( $p->get_image_id(), 'large' ) : '';
			$base  = array( 'product_id' => $p->get_id(), 'parent_name' => $p->get_name(), 'voucher' => 'yes' === get_post_meta( $p->get_id(), self::meta( 'enable' ), true ), 'url' => get_permalink( $p->get_id() ), 'image' => $image ? $image : '',
				// 1.3.0: the categories, to filter the list in Spa Booking.
				'categories' => self::product_categories( $p->get_id() ), 'status' => $p->get_status(), 'stock_status' => $p->get_stock_status() );
			if ( $p->is_type( 'variable' ) ) {
				foreach ( $p->get_children() as $vid ) {
					$v = wc_get_product( $vid );
					if ( ! $v ) {
						continue;
					}
					// 1.6.0: whether the variation is enabled (sold on the site) and its own stock.
					$out[] = $base + array( 'variation_id' => $vid, 'name' => $v->get_name(), 'sku' => $v->get_sku(), 'price' => (float) $v->get_price(),
						'enabled' => 'publish' === $v->get_status(), 'variation_stock_status' => $v->get_stock_status() );
				}
			} else {
				$out[] = $base + array( 'variation_id' => 0, 'name' => $p->get_name(), 'sku' => $p->get_sku(), 'price' => (float) $p->get_price() );
			}
		}
		return array( 'products' => $out, 'categories' => self::all_categories() );
	}

	/* ---------------------------------------------- products (1.3.0) */

	private static function product_categories( $product_id ) {
		$terms = get_the_terms( $product_id, 'product_cat' );
		$out   = array();
		foreach ( is_array( $terms ) ? $terms : array() as $term ) {
			$out[] = array( 'id' => (int) $term->term_id, 'name' => html_entity_decode( $term->name ) );
		}
		return $out;
	}

	private static function all_categories() {
		$terms = get_terms( array( 'taxonomy' => 'product_cat', 'hide_empty' => false ) );
		$out   = array();
		foreach ( is_array( $terms ) ? $terms : array() as $term ) {
			$out[] = array( 'id' => (int) $term->term_id, 'name' => html_entity_decode( $term->name ), 'parent' => (int) $term->parent, 'count' => (int) $term->count );
		}
		return $out;
	}

	/** One product with what Spa Booking lets the desk change. */
	public static function product( WP_REST_Request $request ) {
		$p = wc_get_product( absint( $request->get_param( 'id' ) ) );
		if ( ! $p || $p->is_type( 'variation' ) ) {
			return new WP_Error( 'not_found', 'Prodotto non trovato', array( 'status' => 404 ) );
		}
		$variations = array();
		if ( $p->is_type( 'variable' ) ) {
			foreach ( $p->get_children() as $vid ) {
				$v = wc_get_product( $vid );
				if ( $v ) {
					$variations[] = array( 'id' => $vid, 'name' => wc_get_formatted_variation( $v, true, false, false ), 'regular_price' => $v->get_regular_price(), 'sale_price' => $v->get_sale_price(), 'stock_status' => $v->get_stock_status(),
						// 1.6.0: «Abilitata» in WooCommerce (a disabled variation is not sold).
						'enabled' => 'publish' === $v->get_status(), 'sku' => $v->get_sku() );
				}
			}
		}
		$image = $p->get_image_id() ? wp_get_attachment_image_url( $p->get_image_id(), 'medium' ) : '';
		return array(
			'id'                => $p->get_id(),
			'type'              => $p->get_type(),
			'status'            => $p->get_status(),
			'name'              => $p->get_name(),
			'short_description' => $p->get_short_description(),
			'description'       => $p->get_description(),
			'regular_price'     => $p->get_regular_price(),
			'sale_price'        => $p->get_sale_price(),
			'sku'               => $p->get_sku(),
			'category_ids'      => array_map( 'intval', $p->get_category_ids() ),
			'stock_status'      => $p->get_stock_status(),
			'manage_stock'      => (bool) $p->get_manage_stock(),
			'stock_quantity'    => $p->get_stock_quantity(),
			'variations'        => $variations,
			'url'               => get_permalink( $p->get_id() ),
			'edit_url'          => admin_url( 'post.php?post=' . $p->get_id() . '&action=edit' ),
			'image'             => $image ? $image : '',
			'categories'        => self::all_categories(),
		);
	}

	private static function clean_price( $value ) {
		if ( null === $value ) {
			return null;
		}
		$value = str_replace( ',', '.', trim( (string) $value ) );
		if ( '' === $value ) {
			return '';
		}
		if ( ! is_numeric( $value ) || (float) $value < 0 ) {
			return false;
		}
		return wc_format_decimal( $value );
	}

	/** Change name, texts, prices and categories of a product (from Spa Booking). */
	public static function product_update( WP_REST_Request $request ) {
		$p = wc_get_product( absint( $request->get_param( 'id' ) ) );
		if ( ! $p || $p->is_type( 'variation' ) ) {
			return new WP_Error( 'not_found', 'Prodotto non trovato', array( 'status' => 404 ) );
		}
		$name = $request->get_param( 'name' );
		if ( null !== $name ) {
			$name = sanitize_text_field( (string) $name );
			if ( '' === $name ) {
				return new WP_Error( 'invalid', 'Il nome non può essere vuoto', array( 'status' => 400 ) );
			}
			$p->set_name( $name );
		}
		foreach ( array( 'description' => 'set_description', 'short_description' => 'set_short_description' ) as $field => $setter ) {
			$value = $request->get_param( $field );
			if ( null !== $value ) {
				$p->$setter( wp_kses_post( (string) $value ) );
			}
		}
		if ( ! $p->is_type( 'variable' ) ) {
			$regular = self::clean_price( $request->get_param( 'regular_price' ) );
			$sale    = self::clean_price( $request->get_param( 'sale_price' ) );
			if ( false === $regular || false === $sale ) {
				return new WP_Error( 'invalid', 'Prezzo non valido', array( 'status' => 400 ) );
			}
			if ( null !== $regular ) {
				$p->set_regular_price( $regular );
			}
			if ( null !== $sale ) {
				$p->set_sale_price( $sale );
			}
			$r = null !== $regular ? $regular : $p->get_regular_price();
			$s = null !== $sale ? $sale : $p->get_sale_price();
			if ( '' !== $s && '' !== $r && (float) $s >= (float) $r ) {
				return new WP_Error( 'invalid', 'Il prezzo in offerta deve essere più basso del prezzo normale', array( 'status' => 400 ) );
			}
		}
		// 1.4.0: published, draft, waiting for review or private; in stock or sold out.
		$status = $request->get_param( 'status' );
		if ( null !== $status ) {
			if ( ! in_array( $status, array( 'publish', 'draft', 'pending', 'private' ), true ) ) {
				return new WP_Error( 'invalid', 'Stato non valido', array( 'status' => 400 ) );
			}
			$p->set_status( $status );
		}
		$stock = $request->get_param( 'stock_status' );
		if ( null !== $stock ) {
			if ( ! in_array( $stock, array( 'instock', 'outofstock', 'onbackorder' ), true ) ) {
				return new WP_Error( 'invalid', 'Disponibilità non valida', array( 'status' => 400 ) );
			}
			if ( $p->is_type( 'variable' ) ) {
				foreach ( $p->get_children() as $vid ) {
					$v = wc_get_product( $vid );
					if ( $v && ! $v->get_manage_stock() ) {
						$v->set_stock_status( $stock );
						$v->save();
					}
				}
			} elseif ( ! $p->get_manage_stock() ) {
				$p->set_stock_status( $stock );
			}
		}
		$quantity = $request->get_param( 'stock_quantity' );
		if ( null !== $quantity && $p->get_manage_stock() ) {
			$p->set_stock_quantity( max( 0, (int) $quantity ) );
		}
		$cats = $request->get_param( 'category_ids' );
		if ( is_array( $cats ) ) {
			$cats = array_values( array_filter( array_map( 'absint', $cats ) ) );
			$p->set_category_ids( $cats );
		}
		$p->save();
		$variations = $request->get_param( 'variations' );
		if ( $p->is_type( 'variable' ) && is_array( $variations ) ) {
			foreach ( $variations as $row ) {
				$v = wc_get_product( absint( $row['id'] ?? 0 ) );
				if ( ! $v || $v->get_parent_id() !== $p->get_id() ) {
					continue;
				}
				$regular = self::clean_price( $row['regular_price'] ?? null );
				$sale    = self::clean_price( $row['sale_price'] ?? null );
				if ( false === $regular || false === $sale ) {
					return new WP_Error( 'invalid', 'Prezzo non valido in una variante', array( 'status' => 400 ) );
				}
				if ( null !== $regular ) {
					$v->set_regular_price( $regular );
				}
				if ( null !== $sale ) {
					$v->set_sale_price( $sale );
				}
				if ( isset( $row['stock_status'] ) && in_array( $row['stock_status'], array( 'instock', 'outofstock', 'onbackorder' ), true ) && ! $v->get_manage_stock() ) {
					$v->set_stock_status( $row['stock_status'] );
				}
				// 1.6.0: enable or disable the variation, as its «Abilitata» box.
				if ( isset( $row['enabled'] ) ) {
					$v->set_status( rest_sanitize_boolean( $row['enabled'] ) ? 'publish' : 'private' );
				}
				$v->save();
			}
			WC_Product_Variable::sync( $p->get_id() );
		}
		wc_delete_product_transients( $p->get_id() );
		return array_merge( array( 'ok' => true ), self::product_by_id( $p->get_id() ) );
	}

	/* ------------------------------------------------- orders (1.4.0) */

	private static function order_row( $order ) {
		$items = array();
		foreach ( $order->get_items() as $item ) {
			$items[] = $item->get_name() . ( $item->get_quantity() > 1 ? ' ×' . $item->get_quantity() : '' );
		}
		return array(
			'id'       => $order->get_id(),
			'number'   => $order->get_order_number(),
			'status'   => $order->get_status(),
			'date'     => $order->get_date_created() ? $order->get_date_created()->date( 'c' ) : '',
			'paid'     => $order->get_date_paid() ? $order->get_date_paid()->date( 'c' ) : '',
			'total'    => (float) $order->get_total(),
			'refunded' => (float) $order->get_total_refunded(),
			'currency' => $order->get_currency(),
			'name'     => trim( $order->get_billing_first_name() . ' ' . $order->get_billing_last_name() ),
			'email'    => $order->get_billing_email(),
			'phone'    => $order->get_billing_phone(),
			'payment'  => $order->get_payment_method_title(),
			'items'    => $items,
		);
	}

	/** The orders of the shop, newest first, a page at a time. */
	public static function orders( WP_REST_Request $request ) {
		$per    = max( 5, min( 100, absint( $request->get_param( 'per_page' ) ?: 30 ) ) );
		$page   = max( 1, absint( $request->get_param( 'page' ) ?: 1 ) );
		$status = sanitize_key( (string) $request->get_param( 'status' ) );
		$search = trim( (string) $request->get_param( 'search' ) );
		$args   = array( 'limit' => $per, 'paged' => $page, 'orderby' => 'date', 'order' => 'DESC', 'paginate' => true, 'type' => 'shop_order' );
		$args['status'] = $status ? array( $status ) : array_keys( wc_get_order_statuses() );
		$counts = array();
		foreach ( array_keys( wc_get_order_statuses() ) as $key ) {
			$counts[ substr( $key, 3 ) ] = (int) wc_orders_count( substr( $key, 3 ) );
		}
		$statuses = array_map( 'html_entity_decode', wc_get_order_statuses() );
		if ( '' !== $search && ctype_digit( ltrim( $search, '#' ) ) ) {
			// An order number: that order alone.
			$one = wc_get_order( absint( ltrim( $search, '#' ) ) );
			$rows = $one && 'shop_order' === $one->get_type() ? array( self::order_row( $one ) ) : array();
			return array( 'orders' => $rows, 'total' => count( $rows ), 'pages' => 1, 'page' => 1, 'counts' => $counts, 'statuses' => $statuses );
		}
		if ( '' !== $search ) {
			if ( is_email( $search ) ) {
				$args['billing_email'] = $search;
			} else {
				$args['s'] = $search;
			}
		}
		$result = wc_get_orders( $args );
		return array(
			'orders' => array_map( array( __CLASS__, 'order_row' ), $result->orders ),
			'total'  => (int) $result->total,
			'pages'  => (int) $result->max_num_pages,
			'page'   => $page,
			'counts' => $counts,
			'statuses' => $statuses,
		);
	}

	/** One order with everything to check it. */
	public static function order( WP_REST_Request $request ) {
		$order = wc_get_order( absint( $request->get_param( 'id' ) ) );
		if ( ! $order || 'shop_order' !== $order->get_type() ) {
			return new WP_Error( 'not_found', 'Ordine non trovato', array( 'status' => 404 ) );
		}
		$items = array();
		foreach ( $order->get_items() as $item_id => $item ) {
			$meta = array();
			foreach ( $item->get_formatted_meta_data( '_', true ) as $m ) {
				$meta[] = array( 'key' => wp_strip_all_tags( $m->display_key ), 'value' => wp_strip_all_tags( $m->display_value ) );
			}
			$items[] = array(
				'name'       => $item->get_name(),
				'quantity'   => (int) $item->get_quantity(),
				'total'      => (float) $item->get_total() + (float) $item->get_total_tax(),
				'product_id' => $item->get_product_id(),
				'variation_id' => $item->get_variation_id(),
				'codes'      => (string) $item->get_meta( self::meta( 'codes' ) ),
				'meta'       => $meta,
			);
		}
		$notes = array();
		foreach ( wc_get_order_notes( array( 'order_id' => $order->get_id(), 'limit' => 30 ) ) as $note ) {
			$notes[] = array( 'text' => wp_strip_all_tags( $note->content ), 'date' => $note->date_created ? $note->date_created->date( 'c' ) : '', 'customer' => (bool) $note->customer_note, 'by' => $note->added_by );
		}
		$coupons = array();
		foreach ( $order->get_coupon_codes() as $code ) {
			$coupons[] = $code;
		}
		$billing = $order->get_address( 'billing' );
		// array_merge: the full items replace the short names of order_row (1.4.1).
		return array_merge( self::order_row( $order ), array(
			'items'          => $items,
			'subtotal'       => (float) $order->get_subtotal(),
			'discount'       => (float) $order->get_total_discount(),
			'tax'            => (float) $order->get_total_tax(),
			'shipping'       => (float) $order->get_shipping_total(),
			'coupons'        => $coupons,
			'billing'        => array_map( 'strval', $billing ),
			'customer_note'  => $order->get_customer_note(),
			'transaction_id' => $order->get_transaction_id(),
			'notes'          => $notes,
			'edit_url'       => $order->get_edit_order_url(),
			'statuses'       => array_map( 'html_entity_decode', wc_get_order_statuses() ),
		) );
	}

	/** Change the state of an order or add a note to it, from Spa Booking. */
	public static function order_update( WP_REST_Request $request ) {
		$order = wc_get_order( absint( $request->get_param( 'id' ) ) );
		if ( ! $order || 'shop_order' !== $order->get_type() ) {
			return new WP_Error( 'not_found', 'Ordine non trovato', array( 'status' => 404 ) );
		}
		$by     = sanitize_text_field( (string) $request->get_param( 'by' ) );
		$status = sanitize_key( (string) $request->get_param( 'status' ) );
		if ( '' !== $status ) {
			// Refunds move money: they stay in WordPress.
			if ( ! in_array( $status, array( 'pending', 'processing', 'on-hold', 'completed', 'cancelled' ), true ) ) {
				return new WP_Error( 'invalid', 'Stato non consentito da Spa Booking', array( 'status' => 400 ) );
			}
			$order->update_status( $status, 'Spa Booking' . ( $by ? ' (' . $by . ')' : '' ) . ': ' );
		}
		$note = trim( wp_strip_all_tags( (string) $request->get_param( 'note' ) ) );
		if ( '' !== $note ) {
			$order->add_order_note( $note . ( $by ? ' — ' . $by : '' ), (bool) $request->get_param( 'customer_note' ) );
		}
		$request->set_param( 'id', $order->get_id() );
		return self::order( $request );
	}

	private static function product_by_id( $id ) {
		$request = new WP_REST_Request( 'GET', '' );
		$request->set_param( 'id', $id );
		$result = self::product( $request );
		return is_array( $result ) ? $result : array();
	}

	/** The voucher codes sold in the last `days` days, with their state. */
	public static function vouchers( WP_REST_Request $request ) {
		$days   = max( 1, min( 800, absint( $request->get_param( 'days' ) ?: 200 ) ) );
		$orders = wc_get_orders( array(
			'limit'        => -1,
			'status'       => array( 'processing', 'completed', 'refunded', 'cancelled' ),
			'date_created' => '>=' . gmdate( 'Y-m-d', time() - $days * DAY_IN_SECONDS ),
			'orderby'      => 'date',
			'order'        => 'DESC',
		) );
		$out = array();
		foreach ( $orders as $order ) {
			$details = $order->get_meta( self::meta( 'meta_order_details' ) );
			foreach ( $order->get_items() as $item_id => $item ) {
				$codes = (string) $item->get_meta( self::meta( 'codes' ) );
				if ( '' === trim( $codes ) ) {
					continue;
				}
				$pid  = $item->get_product_id();
				$vid  = $item->get_variation_id();
				$info = is_array( $details ) && isset( $details[ $pid ] ) ? $details[ $pid ] : array();
				$exp  = isset( $info['exp_date'] ) ? ( is_array( $info['exp_date'] ) ? ( $info['exp_date'][ $vid ] ?? reset( $info['exp_date'] ) ) : $info['exp_date'] ) : '';
				foreach ( array_filter( array_map( 'trim', explode( ',', $codes ) ) ) as $code ) {
					$code_post = self::code_post( $code );
					$state     = self::code_state( $code, $code_post ? $code_post->ID : 0 );
					// 1.7.0: the code's own date first — the one «Buoni PDF»
					// checks and the one an extension changes — then the order's.
					$own = $code_post ? (string) get_post_meta( $code_post->ID, self::meta( 'exp_date' ), true ) : '';
					$out[] = array(
						'code'            => $code,
						'order_id'        => $order->get_id(),
						'order_status'    => $order->get_status(),
						'order_date'      => $order->get_date_created() ? $order->get_date_created()->date( 'c' ) : '',
						'product_id'      => $pid,
						'variation_id'    => $vid,
						'product_name'    => $item->get_name(),
						'value'           => (float) ( $item->get_meta( self::meta( 'voucher_price' ) ) ?: ( $item->get_total() + $item->get_total_tax() ) / max( 1, $item->get_quantity() ) ),
						'expires'         => '' !== $own ? substr( $own, 0, 10 ) : ( $exp ? substr( (string) $exp, 0, 10 ) : '' ),
						'buyer_first'     => $order->get_billing_first_name(),
						'buyer_last'      => $order->get_billing_last_name(),
						'buyer_email'     => $order->get_billing_email(),
						'buyer_phone'     => $order->get_billing_phone(),
						'recipient_name'  => self::labelled( $item->get_meta( self::meta( 'recipient_name' ) ) ),
						'recipient_email' => self::labelled( $item->get_meta( self::meta( 'recipient_email' ) ) ),
						'message'         => self::labelled( $item->get_meta( self::meta( 'recipient_message' ) ) ),
						'used'            => $state['used'],
						'used_at'         => $state['used_at'],
					);
				}
			}
		}
		return array( 'vouchers' => $out, 'days' => $days );
	}

	/** Mark a code redeemed in «Buoni PDF», as the desk would from «Riscatta voucher». */
	public static function redeem( WP_REST_Request $request ) {
		$code = trim( (string) $request->get_param( 'code' ) );
		$post = self::code_post( $code );
		if ( ! $post ) {
			return new WP_Error( 'not_found', 'Codice voucher non trovato', array( 'status' => 404 ) );
		}
		$code  = self::exact_code( $post->ID, $code );
		$state = self::code_state( $code, $post->ID );
		if ( $state['used'] ) {
			return array( 'ok' => true, 'already' => true, 'used_at' => $state['used_at'] );
		}
		$user = self::options()['redeem_user'] ?: get_current_user_id();
		$now  = current_time( 'mysql' );
		$used = trim( (string) get_post_meta( $post->ID, self::meta( 'used_codes' ), true ) );
		update_post_meta( $post->ID, self::meta( 'used_codes' ), $used ? $used . ',' . $code : $code );
		update_post_meta( $post->ID, self::meta( 'used_time' ), $now );
		update_post_meta( $post->ID, self::meta( 'redeem_by' ), $user );
		update_post_meta( $post->ID, self::meta( 'redeem_method' ), 'full' );
		$order_id = (int) get_post_meta( $post->ID, self::meta( 'order_id' ), true );
		$order    = $order_id ? wc_get_order( $order_id ) : null;
		$note     = trim( (string) $request->get_param( 'note' ) );
		if ( $order ) {
			$order->add_order_note( sprintf( 'Voucher %s riscattato in spa (Spa Booking)%s.', $code, $note ? ' · ' . $note : '' ) );
		}
		do_action( 'spa_booking_connector_redeemed', $code, $post->ID, $order_id );
		return array( 'ok' => true, 'code' => $code, 'used_at' => $now );
	}

	/**
	 * A new expiry date for a code (1.7.0), as «Estendi la data di scadenza»
	 * in «Buoni PDF»: also for an expired code, never for a used one. The
	 * time of day already stored is kept (end of the day when there is none).
	 */
	public static function voucher_expiry( WP_REST_Request $request ) {
		$code    = trim( (string) $request->get_param( 'code' ) );
		$expires = trim( (string) $request->get_param( 'expires' ) );
		$date    = DateTime::createFromFormat( '!Y-m-d', $expires );
		if ( ! $date || $date->format( 'Y-m-d' ) !== $expires ) {
			return new WP_Error( 'bad_date', 'Data di scadenza non valida', array( 'status' => 400 ) );
		}
		$post = self::code_post( $code );
		if ( ! $post ) {
			return new WP_Error( 'not_found', 'Codice voucher non trovato', array( 'status' => 404 ) );
		}
		$code  = self::exact_code( $post->ID, $code );
		$state = self::code_state( $code, $post->ID );
		if ( $state['used'] ) {
			return new WP_Error( 'used', 'Il voucher è già stato riscattato', array( 'status' => 409 ) );
		}
		$key      = self::meta( 'exp_date' );
		$previous = (string) get_post_meta( $post->ID, $key, true );
		$time     = preg_match( '/\d{2}:\d{2}:\d{2}$/', $previous, $m ) ? $m[0] : '23:59:59';
		update_post_meta( $post->ID, $key, $expires . ' ' . $time );
		$order_id = (int) get_post_meta( $post->ID, self::meta( 'order_id' ), true );
		$order    = $order_id ? wc_get_order( $order_id ) : null;
		if ( $order ) {
			$by = trim( wp_strip_all_tags( (string) $request->get_param( 'by' ) ) );
			$order->add_order_note( sprintf( 'Scadenza del voucher %s portata al %s (Spa Booking%s)%s.', $code,
				$date->format( 'd/m/Y' ), $by ? ', ' . $by : '', $previous ? ', prima ' . mysql2date( 'd/m/Y', $previous ) : '' ) );
		}
		do_action( 'spa_booking_connector_voucher_expiry', $code, $post->ID, $expires, $previous );
		return array( 'ok' => true, 'code' => $code, 'expires' => $expires, 'previous' => $previous ? substr( $previous, 0, 10 ) : '' );
	}

	/** What «Buoni PDF» stores for one code, to check the fields on this site. */
	public static function diag( WP_REST_Request $request ) {
		$post = self::code_post( trim( (string) $request->get_param( 'code' ) ) );
		if ( ! $post ) {
			return array( 'found' => false, 'post_type' => self::code_type() );
		}
		$meta = array();
		foreach ( get_post_meta( $post->ID ) as $key => $values ) {
			$meta[ $key ] = maybe_unserialize( $values[0] );
		}
		return array( 'found' => true, 'id' => $post->ID, 'status' => $post->post_status, 'parent' => $post->post_parent, 'meta' => $meta );
	}

	/* ------------------------------------------------- contacts (1.2.0) */

	/**
	 * The people of the site: newsletter subscribers («Newsletter» plugin),
	 * the shop's buyers (from the orders) and the newsletter discount codes
	 * (coupons tied to one e-mail whose code starts with `prefix`).
	 */
	public static function contacts( WP_REST_Request $request ) {
		$prefix = strtolower( trim( (string) ( $request->get_param( 'prefix' ) ?? 'welcome' ) ) );
		return array(
			'newsletter' => self::newsletter_people(),
			'buyers'     => self::buyers(),
			'coupons'    => self::newsletter_coupons( $prefix ),
			'prefix'     => $prefix,
		);
	}

	private static function newsletter_table() {
		global $wpdb;
		$table = $wpdb->prefix . 'newsletter';
		return $wpdb->get_var( $wpdb->prepare( 'SHOW TABLES LIKE %s', $table ) ) === $table ? $table : '';
	}

	private static function newsletter_people() {
		global $wpdb;
		$table = self::newsletter_table();
		if ( '' === $table ) {
			return array();
		}
		// The phone is one of the profile fields, if the form asked for it.
		$phone_col = '';
		$profile   = get_option( 'newsletter_profile', array() );
		if ( is_array( $profile ) ) {
			for ( $i = 1; $i <= 20; $i++ ) {
				$label = strtolower( (string) ( $profile[ 'profile_' . $i ] ?? '' ) );
				if ( '' !== $label && preg_match( '/tel|cell|phone|whats/', $label ) ) {
					$phone_col = 'profile_' . $i;
					break;
				}
			}
		}
		$columns = $wpdb->get_col( "SHOW COLUMNS FROM `$table`", 0 );
		$fields  = array( 'email', 'name', 'surname', 'status', 'created' );
		if ( $phone_col && in_array( $phone_col, $columns, true ) ) {
			$fields[] = $phone_col;
		}
		$fields = array_values( array_intersect( $fields, $columns ) );
		$rows   = $wpdb->get_results( 'SELECT `' . implode( '`,`', $fields ) . "` FROM `$table` ORDER BY id DESC LIMIT 20000", ARRAY_A );
		$out    = array();
		foreach ( (array) $rows as $row ) {
			$email = sanitize_email( $row['email'] ?? '' );
			if ( '' === $email ) {
				continue;
			}
			$out[] = array(
				'email'   => $email,
				'first'   => (string) ( $row['name'] ?? '' ),
				'last'    => (string) ( $row['surname'] ?? '' ),
				'phone'   => $phone_col ? (string) ( $row[ $phone_col ] ?? '' ) : '',
				// C = confirmed, S = not confirmed yet, U = unsubscribed, B = bounced, P = complained.
				'status'  => (string) ( $row['status'] ?? '' ),
				'created' => (string) ( $row['created'] ?? '' ),
			);
		}
		return $out;
	}

	private static function buyers() {
		if ( ! function_exists( 'wc_get_orders' ) ) {
			return array();
		}
		$by = array();
		$page = 1;
		do {
			$orders = wc_get_orders( array(
				'limit'   => 200,
				'paged'   => $page,
				'status'  => array( 'processing', 'completed', 'on-hold', 'refunded' ),
				'orderby' => 'date',
				'order'   => 'ASC',
				'type'    => 'shop_order',
			) );
			foreach ( $orders as $order ) {
				$email = strtolower( sanitize_email( $order->get_billing_email() ) );
				if ( '' === $email ) {
					continue;
				}
				$paid = 'refunded' === $order->get_status() ? 0.0 : (float) $order->get_total() - (float) $order->get_total_refunded();
				$when = $order->get_date_created() ? $order->get_date_created()->date( 'c' ) : '';
				if ( ! isset( $by[ $email ] ) ) {
					$by[ $email ] = array( 'email' => $email, 'orders' => 0, 'total' => 0.0, 'first_order' => $when );
				}
				$by[ $email ]['first']      = $order->get_billing_first_name() ?: ( $by[ $email ]['first'] ?? '' );
				$by[ $email ]['last']       = $order->get_billing_last_name() ?: ( $by[ $email ]['last'] ?? '' );
				$by[ $email ]['phone']      = $order->get_billing_phone() ?: ( $by[ $email ]['phone'] ?? '' );
				$by[ $email ]['orders']    += 1;
				$by[ $email ]['total']     += max( 0.0, $paid );
				$by[ $email ]['last_order'] = $when;
			}
			$page++;
		} while ( count( $orders ) === 200 && $page < 200 );
		foreach ( $by as &$row ) {
			$row['total'] = round( $row['total'], 2 );
		}
		unset( $row );
		return array_values( $by );
	}

	private static function newsletter_coupons( $prefix ) {
		$ids = get_posts( array( 'post_type' => 'shop_coupon', 'post_status' => 'publish', 'posts_per_page' => -1, 'fields' => 'ids' ) );
		$out = array();
		foreach ( $ids as $id ) {
			$coupon = new WC_Coupon( $id );
			$code   = (string) $coupon->get_code();
			$emails = (array) $coupon->get_email_restrictions();
			if ( '' === $code || 1 !== count( $emails ) || ( '' !== $prefix && 0 !== strpos( strtolower( $code ), $prefix ) ) ) {
				continue;
			}
			$expires = $coupon->get_date_expires();
			$limit   = (int) $coupon->get_usage_limit();
			$per     = (int) $coupon->get_usage_limit_per_user();
			$count   = (int) $coupon->get_usage_count();
			$out[]   = array(
				'id'         => $id,
				'code'       => $code,
				'email'      => strtolower( (string) reset( $emails ) ),
				'type'       => $coupon->get_discount_type(),
				'amount'     => (float) $coupon->get_amount(),
				'min_amount' => (float) $coupon->get_minimum_amount(),
				'expires'    => $expires ? $expires->date( 'Y-m-d' ) : '',
				'created'    => $coupon->get_date_created() ? $coupon->get_date_created()->date( 'c' ) : '',
				'used'       => $count > 0 && ( $count >= max( 1, $limit ?: $per ?: 1 ) ),
				'used_count' => $count,
			);
		}
		return $out;
	}

	/** The desk used a newsletter code in the spa: it cannot be used again on the shop. */
	public static function coupon_use( WP_REST_Request $request ) {
		$code = trim( (string) $request->get_param( 'code' ) );
		$id   = $code ? wc_get_coupon_id_by_code( $code ) : 0;
		if ( ! $id ) {
			return new WP_Error( 'not_found', 'Codice sconto non trovato', array( 'status' => 404 ) );
		}
		$coupon = new WC_Coupon( $id );
		if ( $coupon->get_usage_count() > 0 ) {
			return array( 'ok' => true, 'already' => true );
		}
		$emails = (array) $coupon->get_email_restrictions();
		$coupon->increase_usage( $emails ? (string) reset( $emails ) : '' );
		$note = trim( (string) $request->get_param( 'note' ) );
		$coupon->set_description( trim( $coupon->get_description() . "\nUsato in spa (Spa Booking) " . current_time( 'mysql' ) . ( $note ? ' · ' . $note : '' ) ) );
		$coupon->save();
		return array( 'ok' => true, 'code' => $code );
	}

	/* ------------------------------------------- gift card (1.8.0) */

	const GIFT_META = '_sbc_gift';

	/**
	 * The gift cards sold in Spa Booking, as WooCommerce coupons: same code,
	 * a fixed discount on the cart worth the credit left, one purchase only,
	 * the same expiry. Spa Booking sends the whole list each time: a card
	 * missing from it (spent at the spa, deleted, expired) is put in the
	 * bin unless it was already used here. A coupon with the same code not
	 * made by Spa Booking is never touched. The answer lists the cards spent
	 * in a paid order, for Spa Booking to close them.
	 */
	public static function gift_cards( WP_REST_Request $request ) {
		if ( ! class_exists( 'WC_Coupon' ) ) {
			return new WP_Error( 'no_woocommerce', 'WooCommerce non è attivo', array( 'status' => 400 ) );
		}
		$cards     = (array) $request->get_param( 'cards' );
		$wanted    = array();
		$published = 0;
		$conflicts = array();
		foreach ( $cards as $card ) {
			$code   = strtoupper( trim( (string) ( $card['code'] ?? '' ) ) );
			$amount = round( (float) ( $card['amount'] ?? 0 ), 2 );
			if ( '' === $code || $amount <= 0 ) {
				continue;
			}
			$wanted[ $code ] = true;
			$id = wc_get_coupon_id_by_code( $code );
			if ( $id && ! get_post_meta( $id, self::GIFT_META, true ) ) {
				$conflicts[] = $code;
				continue;
			}
			$coupon = new WC_Coupon( $id ? $id : 0 );
			if ( $id && $coupon->get_usage_count() > 0 ) {
				continue; // spent here: Spa Booking closes it from the answer
			}
			$coupon->set_code( $code );
			$coupon->set_discount_type( 'fixed_cart' );
			$coupon->set_amount( $amount );
			$coupon->set_usage_limit( 1 );
			$coupon->set_individual_use( false );
			$coupon->set_free_shipping( false );
			$expires = trim( (string) ( $card['expires'] ?? '' ) );
			$coupon->set_date_expires( $expires ? strtotime( $expires . ' 23:59:59 ' . wp_timezone_string() ) : null );
			$label = trim( (string) ( $card['label'] ?? '' ) );
			$coupon->set_description( 'Gift card Spa Booking' . ( $label ? ' · ' . $label : '' ) . ' — una sola volta, il credito non usato non resta.' );
			$coupon->save();
			update_post_meta( $coupon->get_id(), self::GIFT_META, 1 );
			if ( 'publish' !== get_post_status( $coupon->get_id() ) ) {
				wp_update_post( array( 'ID' => $coupon->get_id(), 'post_status' => 'publish' ) );
			}
			$published++;
		}
		$used    = array();
		$removed = 0;
		$ids     = get_posts( array( 'post_type' => 'shop_coupon', 'post_status' => array( 'publish', 'draft', 'pending', 'private' ), 'posts_per_page' => -1, 'fields' => 'ids', 'meta_key' => self::GIFT_META ) );
		foreach ( $ids as $id ) {
			$coupon = new WC_Coupon( $id );
			$code   = strtoupper( (string) $coupon->get_code() );
			$order  = (int) get_post_meta( $id, '_sbc_order', true );
			if ( $order ) {
				$used[] = array(
					'code'     => $code,
					'order_id' => $order,
					'amount'   => (float) get_post_meta( $id, '_sbc_used_amount', true ),
					'at'       => (string) get_post_meta( $id, '_sbc_used_at', true ),
				);
				continue;
			}
			if ( ! isset( $wanted[ $code ] ) && $coupon->get_usage_count() === 0 ) {
				wp_trash_post( $id );
				$removed++;
			}
		}
		return array( 'ok' => true, 'published' => $published, 'removed' => $removed, 'conflicts' => $conflicts, 'used' => $used );
	}

	/** A paid order with a Spa Booking gift card: remember which. */
	public static function gift_used( $order_id ) {
		$order = wc_get_order( $order_id );
		if ( ! $order ) {
			return;
		}
		foreach ( $order->get_items( 'coupon' ) as $item ) {
			$id = wc_get_coupon_id_by_code( $item->get_code() );
			if ( ! $id || ! get_post_meta( $id, self::GIFT_META, true ) ) {
				continue;
			}
			update_post_meta( $id, '_sbc_order', (int) $order_id );
			update_post_meta( $id, '_sbc_used_amount', round( (float) $item->get_discount() + (float) $item->get_discount_tax(), 2 ) );
			update_post_meta( $id, '_sbc_used_at', current_time( 'c' ) );
		}
	}

	/** The order is cancelled or refunded: the card is not spent any more. */
	public static function gift_back( $order_id ) {
		$order = wc_get_order( $order_id );
		if ( ! $order ) {
			return;
		}
		foreach ( $order->get_items( 'coupon' ) as $item ) {
			$id = wc_get_coupon_id_by_code( $item->get_code() );
			if ( $id && (int) get_post_meta( $id, '_sbc_order', true ) === (int) $order_id ) {
				delete_post_meta( $id, '_sbc_order' );
				delete_post_meta( $id, '_sbc_used_amount' );
				delete_post_meta( $id, '_sbc_used_at' );
			}
		}
	}

	/* --------------------------------------------------------- Buoni PDF */

	private static function vou_active() {
		return defined( 'WOO_VOU_PLUGIN_VERSION' ) || class_exists( 'WOO_Vou_Model' ) || post_type_exists( self::code_type() );
	}

	private static function meta( $name ) {
		return ( defined( 'WOO_VOU_META_PREFIX' ) ? WOO_VOU_META_PREFIX : '_woo_vou_' ) . $name;
	}

	private static function code_type() {
		return defined( 'WOO_VOU_CODE_POST_TYPE' ) ? WOO_VOU_CODE_POST_TYPE : 'woovouchercodes';
	}

	private static function code_post( $code ) {
		if ( '' === $code ) {
			return null;
		}
		$posts = get_posts( array(
			'post_type'      => self::code_type(),
			'post_status'    => 'any',
			'posts_per_page' => 5,
			'meta_query'     => array( array( 'key' => self::meta( 'purchased_codes' ), 'value' => $code, 'compare' => 'LIKE' ) ),
		) );
		foreach ( $posts as $post ) {
			$codes = array_map( 'trim', explode( ',', (string) get_post_meta( $post->ID, self::meta( 'purchased_codes' ), true ) ) );
			foreach ( $codes as $c ) {
				if ( 0 === strcasecmp( $c, $code ) ) {
					return $post;
				}
			}
		}
		return null;
	}

	private static function exact_code( $post_id, $code ) {
		foreach ( array_map( 'trim', explode( ',', (string) get_post_meta( $post_id, self::meta( 'purchased_codes' ), true ) ) ) as $c ) {
			if ( 0 === strcasecmp( $c, $code ) ) {
				return $c;
			}
		}
		return $code;
	}

	private static function code_state( $code, $post_id = 0 ) {
		if ( ! $post_id ) {
			$post    = self::code_post( $code );
			$post_id = $post ? $post->ID : 0;
		}
		if ( ! $post_id ) {
			return array( 'used' => false, 'used_at' => '' );
		}
		$used = array_map( 'trim', explode( ',', (string) get_post_meta( $post_id, self::meta( 'used_codes' ), true ) ) );
		$is   = false;
		foreach ( $used as $c ) {
			if ( '' !== $c && 0 === strcasecmp( $c, $code ) ) {
				$is = true;
			}
		}
		return array( 'used' => $is, 'used_at' => $is ? (string) get_post_meta( $post_id, self::meta( 'used_time' ), true ) : '' );
	}

	private static function labelled( $value ) {
		if ( is_array( $value ) ) {
			return (string) ( $value['value'] ?? '' );
		}
		return (string) $value;
	}

	/* -------------------------------------------------------------- notify */

	public static function notify( $order_id ) {
		$o = self::options();
		if ( empty( $o['notify_url'] ) || empty( $o['secret'] ) ) {
			return;
		}
		$body = wp_json_encode( array( 'order_id' => (int) $order_id, 'time' => time() ) );
		wp_remote_post( $o['notify_url'], array(
			'timeout'  => 5,
			'blocking' => false,
			'headers'  => array(
				'Content-Type'      => 'application/json',
				'X-Spa-Booking-Key' => $o['secret'],
			),
			'body'     => $body,
		) );
	}
}

Spa_Booking_Connector::init();
require_once __DIR__ . '/shop-style.php';
