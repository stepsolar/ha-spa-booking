<?php
/**
 * Plugin Name: Spa Booking Connector
 * Description: Collega lo shop WooCommerce («Buoni PDF») a Spa Booking su Home Assistant: invia i voucher venduti e segna come riscattati quelli usati in spa.
 * Version: 1.0.0
 * Author: Spa Booking
 * Requires PHP: 7.4
 * Text Domain: spa-booking-connector
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class Spa_Booking_Connector {
	const VERSION   = '1.0.0';
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
	}

	/* ------------------------------------------------------------ settings */

	public static function options() {
		$o = get_option( self::OPTION, array() );
		return wp_parse_args( is_array( $o ) ? $o : array(), array( 'secret' => '', 'notify_url' => '', 'redeem_user' => 0 ) );
	}

	public static function register_settings() {
		register_setting( 'spa_booking_connector', self::OPTION, array(
			'type'              => 'array',
			'sanitize_callback' => function ( $in ) {
				return array(
					'secret'      => sanitize_text_field( $in['secret'] ?? '' ),
					'notify_url'  => esc_url_raw( trim( $in['notify_url'] ?? '' ) ),
					'redeem_user' => absint( $in['redeem_user'] ?? 0 ),
				);
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
		register_rest_route( self::NAMESPACE, '/vouchers', array( 'methods' => 'GET', 'callback' => array( __CLASS__, 'vouchers' ), 'permission_callback' => $auth ) );
		register_rest_route( self::NAMESPACE, '/redeem', array( 'methods' => 'POST', 'callback' => array( __CLASS__, 'redeem' ), 'permission_callback' => $auth ) );
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
			'site'        => get_bloginfo( 'name' ),
		);
	}

	/** Every product and variation, to pair with the treatments. */
	public static function products() {
		$out = array();
		$ids = wc_get_products( array( 'status' => array( 'publish', 'private' ), 'limit' => 500, 'return' => 'ids' ) );
		foreach ( $ids as $id ) {
			$p = wc_get_product( $id );
			if ( ! $p ) {
				continue;
			}
			$base = array( 'product_id' => $p->get_id(), 'parent_name' => $p->get_name(), 'voucher' => 'yes' === get_post_meta( $p->get_id(), self::meta( 'enable' ), true ) );
			if ( $p->is_type( 'variable' ) ) {
				foreach ( $p->get_children() as $vid ) {
					$v = wc_get_product( $vid );
					if ( ! $v ) {
						continue;
					}
					$out[] = $base + array( 'variation_id' => $vid, 'name' => $v->get_name(), 'sku' => $v->get_sku(), 'price' => (float) $v->get_price() );
				}
			} else {
				$out[] = $base + array( 'variation_id' => 0, 'name' => $p->get_name(), 'sku' => $p->get_sku(), 'price' => (float) $p->get_price() );
			}
		}
		return array( 'products' => $out );
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
					$state = self::code_state( $code );
					$out[] = array(
						'code'            => $code,
						'order_id'        => $order->get_id(),
						'order_status'    => $order->get_status(),
						'order_date'      => $order->get_date_created() ? $order->get_date_created()->date( 'c' ) : '',
						'product_id'      => $pid,
						'variation_id'    => $vid,
						'product_name'    => $item->get_name(),
						'value'           => (float) ( $item->get_meta( self::meta( 'voucher_price' ) ) ?: ( $item->get_total() + $item->get_total_tax() ) / max( 1, $item->get_quantity() ) ),
						'expires'         => $exp ? substr( (string) $exp, 0, 10 ) : '',
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
