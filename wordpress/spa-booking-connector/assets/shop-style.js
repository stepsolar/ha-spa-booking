/* Spa Booking Connector — «Stile shop», product page.
 * Only adds things around WooCommerce's own form: the original select,
 * radios and fields stay in the page and are what gets submitted.
 * Other plugins (deposits, PDF vouchers) redraw their parts when a variation
 * is chosen, so everything here is idempotent and re-applied on changes. */
(function ($) {
	'use strict';

	var form = document.querySelector('.sbc-style form.cart');
	if (!form || form.getAttribute('data-sbc-ready')) { return; } // once only
	form.setAttribute('data-sbc-ready', '1');

	var variations = [];
	try { variations = JSON.parse(form.getAttribute('data-product_variations') || '[]') || []; } catch (e) { variations = []; }
	var current = null; // the chosen variation, or null
	var button = form.querySelector('.single_add_to_cart_button');
	var buttonText = button ? button.textContent.trim() : '';

	function money(n) {
		return (Math.round(n * 100) / 100).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
	}

	function step(text, cls) {
		var h = document.createElement('div');
		h.className = 'sbc-step ' + cls;
		h.textContent = text;
		return h;
	}

	function ucfirst(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

	/* -------------------------------------------- step 1: the formula */

	var table = form.querySelector('table.variations');
	var syncs = []; // re-run after WooCommerce rebuilds the options
	if (table) {
		table.parentNode.insertBefore(step('Scegli la formula', 'sbc-step-formula'), table);
		var selects = table.querySelectorAll('select');
		var single = selects.length === 1;
		table.classList.add('sbc-has-boxes');
		selects.forEach(function (sel) {
			var name = sel.getAttribute('name');
			var box = document.createElement('div');
			box.className = 'sbc-opts';
			if (!single) {
				var lab = table.querySelector('label[for="' + sel.id + '"]');
				if (lab) {
					var t = document.createElement('div');
					t.className = 'sbc-attr-name';
					t.textContent = lab.textContent;
					sel.parentNode.insertBefore(t, sel);
				}
			}
			Array.prototype.forEach.call(sel.options, function (o) {
				if (!o.value) { return; }
				var b = document.createElement('button');
				b.type = 'button';
				b.className = 'sbc-opt';
				b.setAttribute('data-value', o.value);
				var span = document.createElement('span');
				span.textContent = ucfirst(o.textContent.trim());
				b.appendChild(span);
				if (single) {
					var v = variations.filter(function (x) { return x.attributes[name] === o.value || x.attributes[name] === ''; })[0];
					if (v && v.display_price !== undefined) {
						var em = document.createElement('em');
						em.textContent = money(v.display_price);
						b.appendChild(em);
					}
					if (v && v.is_in_stock === false) { b.disabled = true; }
				}
				b.addEventListener('click', function () {
					$(sel).val(o.value).trigger('change');
				});
				box.appendChild(b);
			});
			sel.classList.add('sbc-hidden');
			sel.parentNode.insertBefore(box, sel);
			// Only what can be bought: WooCommerce leaves in the select just the
			// options of enabled, purchasable variations (a disabled one, «Abilitata»
			// off, is not in data-product_variations either).
			function sellable(value) {
				var opt = Array.prototype.filter.call(sel.options, function (o) { return o.value === value; })[0];
				if (!opt || opt.disabled) { return false; }
				if (single && variations.length) {
					return variations.some(function (x) {
						return (x.attributes[name] === value || x.attributes[name] === '') && x.variation_is_active !== false && x.variation_is_visible !== false;
					});
				}
				return true;
			}
			function sync() {
				box.querySelectorAll('.sbc-opt').forEach(function (b) {
					var value = b.getAttribute('data-value');
					var on = value === sel.value;
					b.hidden = !sellable(value);
					b.classList.toggle('on', on);
					b.setAttribute('aria-pressed', on ? 'true' : 'false');
				});
			}
			syncs.push(sync);
			$(sel).on('change', sync);
			sync();
		});
	}

	/* ---------------------- steps 2 and 3: payment, then the voucher */

	var payStep = step('Come vuoi pagare', 'sbc-step-pay');
	var vouStep = step('Il voucher', 'sbc-step-vou');

	function pct() {
		var amt = form.querySelector('#awcdp-deposit-amount');
		var m = amt && /([\d.,]+)\s*%/.exec(amt.textContent);
		return m ? parseFloat(m[1].replace(',', '.')) / 100 : null;
	}

	function decorate() {
		var deposits = form.querySelector('.awcdp-deposits-wrapper');
		var vou = form.querySelector('.woo-vou-fields-main-wrapper');
		// Payment first: its heading and box go before the voucher (DOM order,
		// so the step numbers follow).
		if (deposits) {
			var placed = payStep.nextSibling === deposits &&
				(!vou || deposits.nextSibling === vouStep || deposits.nextSibling === vou);
			if (!placed) {
				var before = vou ? (vouStep.parentNode === vou.parentNode ? vouStep : vou) : deposits;
				before.parentNode.insertBefore(payStep, before);
				payStep.parentNode.insertBefore(deposits, payStep.nextSibling);
			}
			deposits.querySelectorAll('.awcdp-radio').forEach(function (r) {
				if (r.getAttribute('data-sbc')) { return; }
				r.setAttribute('data-sbc', '1');
				var label = r.querySelector('label');
				var input = r.querySelector('input');
				if (label) {
					// «Paga Deposito (se è per te)» → «Paga Deposito» + small «Se è per te».
					var mm = /^([\s\S]*?)\s*\(([\s\S]+)\)\s*$/.exec(label.textContent.trim());
					if (mm) {
						label.textContent = mm[1];
						var sm = document.createElement('small');
						sm.textContent = ucfirst(mm[2]);
						label.appendChild(sm);
					}
				}
				var a = document.createElement('span');
				a.className = 'sbc-amt';
				r.appendChild(a);
				r.addEventListener('click', function (ev) {
					if (input && ev.target !== input && ev.target.tagName !== 'LABEL') {
						input.checked = true;
						$(input).trigger('change');
					}
				});
			});
		}
		if (vou && vouStep.nextSibling !== vou) {
			vou.parentNode.insertBefore(vouStep, vou);
		}
	}

	/* ------------------------------------------------ prices and button */

	function basePrice() {
		if (current && current.display_price !== undefined) { return current.display_price; }
		if (!table) {
			var p = document.querySelector('.sbc-style div.product .summary > .price ins .amount, .sbc-style div.product .summary > .price > .amount');
			if (p) {
				var n = parseFloat(p.textContent.replace(/[^\d,]/g, '').replace(',', '.'));
				return isNaN(n) ? null : n;
			}
		}
		return null;
	}

	function paint() {
		var price = basePrice();
		var share = pct();
		var depositOn = false;
		form.querySelectorAll('.awcdp-deposits-wrapper .awcdp-radio').forEach(function (r) {
			var input = r.querySelector('input');
			var on = !!(input && input.checked);
			r.classList.toggle('sbc-on', on);
			var full = r.classList.contains('pay-full');
			if (on && !full) { depositOn = true; }
			var a = r.querySelector('.sbc-amt');
			if (a) {
				var text = price === null ? '' : money(full || share === null ? price : price * share);
				if (a.textContent !== text) { a.textContent = text; }
			}
		});
		var vou = form.querySelector('.woo-vou-fields-main-wrapper');
		if (vou) {
			var visible = Array.prototype.some.call(vou.querySelectorAll('table.woo-vou-recipient-fields'), function (w) {
				return w.offsetParent !== null;
			});
			vouStep.style.display = visible ? '' : 'none';
		}
		if (button) {
			var qty = form.querySelector('input.qty');
			var label = buttonText;
			if (price !== null) {
				var q = qty ? Math.max(1, parseInt(qty.value, 10) || 1) : 1;
				label += ' · ' + money((depositOn && share !== null ? price * share : price) * q);
			}
			if (button.textContent !== label) { button.textContent = label; }
		}
	}

	/* -------------------------------------------------------- the loop */

	var observer = new MutationObserver(schedule);
	var pending = false;
	function run() {
		pending = false;
		observer.disconnect();
		decorate();
		syncs.forEach(function (fn) { fn(); });
		paint();
		observer.observe(form, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });
	}
	function schedule() {
		if (!pending) {
			pending = true;
			window.requestAnimationFrame(run);
		}
	}

	$(form).on('found_variation', function (e, v) { current = v; schedule(); });
	$(form).on('reset_data hide_variation', function () { current = null; schedule(); });
	$(form).on('show_variation woocommerce_update_variation_values', schedule);
	$(form).on('change input', 'input', schedule);
	run();
})(jQuery);
