"""
Casos de uso completos del formulario de tratamiento (ver farm/tests/form_cycle.py para el método).

Cada test: teclear en el formulario real (JS real en jsdom) → POST real → base de datos contra valores calculados a mano
→ reabrir la edición y comparar el TEXTO mostrado → guardar sin tocar nada 3 veces y exigir base de datos idéntica.
Escenario base: parcela A de 4,2 ha, cuba de 2000 L, 1000 L de agua/ha → 4200 L de caldo; B = 2,8 ha; C = 6,5 ha.
"""
from decimal import Decimal

from farm.models import Treatment
from farm.tests.form_cycle import (SUBMIT, S_date, S_done, S_dose, S_fields, S_machine, S_partial, S_product, S_remove, S_set,
                                   S_total, S_type, S_clear_total, FormCycleTestCase, es, eur)


class UseCaseBase(FormCycleTestCase):
    def new_spraying(self, product, dose=None, total=None, field=None, water=1000, name='Tratamiento', extra=()):
        steps = [S_type('spraying'), S_set('name', name), S_set('water', water), S_fields((field or self.fA).pk),
                 S_machine(self.m2000.pk), S_product(product.pk)]
        if dose is not None:
            steps.append(S_dose(1, dose))
        if total is not None:
            steps.append(S_total(1, total))
        t, view = self.type_and_save_new(steps + list(extra))
        return t

    def new_fertigation(self, product, dose=None, total=None, field=None, name='Fertirriego'):
        steps = [S_type('fertigation'), S_set('name', name), S_fields((field or self.fB).pk), S_product(product.pk)]
        if dose is not None:
            steps.append(S_dose(1, dose))
        if total is not None:
            steps.append(S_total(1, total))
        t, view = self.type_and_save_new(steps)
        return t

    def reopen_and_check(self, t, context):
        """Pantalla de edición = lo guardado, y 3 ciclos abrir→guardar sin tocar dejan la base de datos idéntica."""
        view, _, _ = self.play(self.open_edit(t), [])
        self.assert_screen_shows_saved(t, view, context=context)
        self.assert_cycle_is_idempotent(t, context=context)
        self.assert_detail_matches(t)
        return view


class Caso1EditarDosisTests(UseCaseBase):
    def test_pulverizacion_editar_dosis_recalcula_total_sin_manual(self):
        """Caso 1: crear con 0,5 L/1000L y editar la dosis a 0,6. Total = 0,6 × 4200 / 1000 = 2,52 L (sin «a mano»)."""
        t = self.new_spraying(self.pL1000, dose='0,5')
        # 0,5 × 4,2 ha × 1000 L/ha / 1000 = 2,1 L; 2,1 × 10 € = 21,00 €; 21 / 4,2 = 5,00 €/ha
        self.assert_db(t, dose='0.5', total='2.1', override=False, unit_price='10.00', total_price='21.00', per_ha='5.00', context='alta')
        t, view = self.type_and_save_edit(t, [S_dose(1, '0,6')])
        # 0,6 × 4200 / 1000 = 2,52 L; × 10 € = 25,20 €; / 4,2 = 6,00 €/ha
        self.assert_db(t, dose='0.6', total='2.52', override=False, unit_price='10.00', total_price='25.20', per_ha='6.00', context='edición')
        shown = self.play(self.open_edit(t), [])[0]['lines'][0]
        self.assertEqual((shown['dose'], shown['total'], shown['cost']), ('0,6', '2,52', '25,20 €'))
        self.reopen_and_check(t, 'dosis 0,6')

    def test_fertirriego_editar_dosis_recalcula_total(self):
        """Caso 1 (fertirriego): 10 L/ha × 2,8 ha = 28 L; editar la dosis a 12 → 33,6 L."""
        t = self.new_fertigation(self.pLHa)
        # 10 × 2,8 = 28 L; 28 × 5 € = 140,00 €; 140 / 2,8 = 50,00 €/ha
        self.assert_db(t, dose='10', total='28', override=False, unit_price='5.00', total_price='140.00', per_ha='50.00', context='alta')
        t, _ = self.type_and_save_edit(t, [S_dose(1, '12')])
        # 12 × 2,8 = 33,6 L; × 5 = 168,00 €; / 2,8 = 60,00 €/ha
        self.assert_db(t, dose='12', total='33.6', override=False, unit_price='5.00', total_price='168.00', per_ha='60.00', context='edición')
        self.reopen_and_check(t, 'fertirriego dosis 12')


class Caso2EditarTotalTests(UseCaseBase):
    def test_pulverizacion_total_25_litros_exacto_y_dosis_derivada(self):
        """Caso 2: un envase de 25 L. total_dose = 25,0000 exacto (no 24,99 ni 25,0026), a mano, dosis derivada coherente."""
        t = self.new_spraying(self.pL1000, dose='0,5')
        t, _ = self.type_and_save_edit(t, [S_total(1, '25')])
        # dosis derivada = 25 × 1000 / (1000 × 4,2) = 5,952380… → 5,9524; coste = 25 × 10 = 250,00; 250 / 4,2 = 59,52 €/ha
        self.assert_db(t, dose='5.9524', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='edición')
        view = self.reopen_and_check(t, 'total 25')
        line = view['lines'][0]
        self.assertEqual((line['dose'], line['total'], line['manual']), ('5,9524', '25', True),
                         f'tecleado=25, guardado={self.line(t).total_dose}, mostrado={line["total"]}')

    def test_fertirriego_total_30_litros_dosis_derivada(self):
        """Caso 3: 10 L/ha × 2,8 ha = 28 L; se cambia el total a 30 L → dosis 30 / 2,8 = 10,714285… → 10,7143."""
        t = self.new_fertigation(self.pLHa)
        t, _ = self.type_and_save_edit(t, [S_total(1, '30')])
        # coste = 30 × 5 = 150,00; 150 / 2,8 = 53,5714… → 53,57 €/ha
        self.assert_db(t, dose='10.7143', total='30', override=True, unit_price='5.00', total_price='150.00', per_ha='53.57', context='edición')
        view = self.reopen_and_check(t, 'fertirriego total 30')
        self.assertEqual((view['lines'][0]['dose'], view['lines'][0]['total']), ('10,7143', '30'))

    def test_total_tecleado_en_el_alta(self):
        """Caso 2 (alta): teclear el total directamente al crear, sin guardar antes sin él."""
        t = self.new_spraying(self.pKg1000, total='50')
        # dosis = 50 × 1000 / 4200 = 11,904761… → 11,9048 kg/1000L; coste = 50 × 9,50 = 475,00; 475 / 4,2 = 113,0952 → 113,10
        self.assert_db(t, dose='11.9048', total='50', override=True, unit_price='9.50', total_price='475.00', per_ha='113.10', context='alta')
        view = self.reopen_and_check(t, 'total 50 en el alta')
        self.assertEqual(view['lines'][0]['total'], '50', f'tecleado=50, guardado={self.line(t).total_dose}, mostrado={view["lines"][0]["total"]}')


class Caso4EditarSinTotalManualTests(UseCaseBase):
    def setUp(self):
        super().setUp()
        self.t = self.new_spraying(self.pL1000, dose='0,5', name='Original')
        self.base = self.db_snapshot(self.t)

    def assert_lines_intact(self, t):
        self.assertEqual(self.db_snapshot(t)['lines'], self.base['lines'])

    def test_cambiar_solo_la_fecha(self):
        """Caso 4: solo la fecha. Dosis y total (0,5 / 2,1) intactos."""
        t, _ = self.type_and_save_edit(self.t, [S_date('2030-06-20')])
        self.assertEqual(str(t.date), '2030-06-20')
        self.assert_lines_intact(t)
        self.reopen_and_check(t, 'solo fecha')

    def test_cambiar_solo_el_nombre(self):
        """Caso 4: solo el nombre."""
        t, _ = self.type_and_save_edit(self.t, [S_set('name', 'Otro nombre')])
        self.assertEqual(t.name, 'Otro nombre')
        self.assert_lines_intact(t)
        self.reopen_and_check(t, 'solo nombre')

    def test_cambiar_solo_la_maquina(self):
        """Caso 4: cambiar la cuba no toca dosis ni total (la cuba solo afecta al reparto por cuba)."""
        t, _ = self.type_and_save_edit(self.t, [S_machine(self.m1000.pk)])
        self.assertEqual(t.machine_id, self.m1000.pk)
        self.assert_lines_intact(t)
        self.reopen_and_check(t, 'solo máquina')


class Caso5EditarConTotalManualTests(UseCaseBase):
    """Tratamiento guardado con total a mano de 25 L (dosis derivada 5,9524 L/1000L sobre 4,2 ha y 1000 L/ha)."""

    def setUp(self):
        super().setUp()
        self.t = self.new_spraying(self.pL1000, total='25', name='Con manual')
        self.assert_db(self.t, dose='5.9524', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='alta')

    def test_cambiar_fecha_y_nombre_mantiene_el_25_exacto(self):
        """Caso 5: fecha y nombre no tocan el total a mano."""
        t, _ = self.type_and_save_edit(self.t, [S_set('name', 'Renombrado'), S_date('2030-06-20')])
        self.assert_db(t, dose='5.9524', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='fecha+nombre')
        self.reopen_and_check(t, 'fecha+nombre con manual')

    def test_cambiar_el_agua_mantiene_el_total_y_rederiva_la_dosis(self):
        """Caso 5 (regla del plan + D1): con 1200 L/ha el caldo es 4,2 × 1200 = 5040 L; dosis = 25 × 1000 / 5040 = 4,9603."""
        t, _ = self.type_and_save_edit(self.t, [S_set('water', 1200)])
        self.assert_db(t, dose='4.9603', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='agua 1200')
        self.reopen_and_check(t, 'agua 1200 con manual')

    def test_tratamiento_parcial_mantiene_el_total_y_rederiva_la_dosis(self):
        """Caso 5: aplicar solo 2 ha de las 4,2. Dosis = 25 × 1000 / (1000 × 2) = 12,5; €/ha = 250 / 2 = 125,00."""
        t, _ = self.type_and_save_edit(self.t, [S_partial('2')])
        self.assertEqual(t.applied_area, Decimal('2'))
        self.assert_db(t, dose='12.5', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='125.00', context='parcial 2 ha')
        self.reopen_and_check(t, 'parcial con manual')

    def test_cambiar_de_parcela_quita_el_total_manual_y_recalcula_desde_la_dosis(self):
        """Caso 5: parcela B (2,8 ha). La dosis que había (5,9524 → 5,953 al redondear hacia arriba a 3 decimales) manda:
        total = 5,953 × 2800 / 1000 = 16,6684 L; coste 166,684 → 166,68; €/ha = 166,68 / 2,8 = 59,5286 → 59,53."""
        t, _ = self.type_and_save_edit(self.t, [S_fields(self.fB.pk)])
        self.assertEqual(t.field_id, self.fB.pk)
        self.assert_db(t, dose='5.953', total='16.6684', override=False, unit_price='10.00', total_price='166.68', per_ha='59.53', context='parcela B')
        self.reopen_and_check(t, 'parcela B')

    def test_cambiar_de_tipo_quita_el_total_manual(self):
        """Caso 5: pulverización → fertirriego con un producto que admite ambos (Foliar L/ha: recomendada 10 L/ha en fertirriego).
        Total = 10 × 4,2 = 42 L; coste 42 × 5 = 210,00; €/ha 50,00."""
        t = self.new_spraying(self.pLHa, total='10', name='Cambio de tipo')
        # 10 L / 4,2 ha = 2,380952… → 2,381 L/ha (4 decimales: 2,3810)
        self.assert_db(t, dose='2.381', total='10', override=True, unit_price='5.00', total_price='50.00', per_ha='11.90', context='alta')
        t, _ = self.type_and_save_edit(t, [S_type('fertigation')])
        self.assertEqual(t.type, 'fertigation')
        self.assert_db(t, dose='10', total='42', override=False, unit_price='5.00', total_price='210.00', per_ha='50.00', context='fertirriego')
        self.reopen_and_check(t, 'cambio de tipo')


class Caso6y7CompletadosTests(UseCaseBase):
    def done_steps(self, finish='2026-10-26', real_water=1200):
        return [S_done(True), S_set('finish', finish), S_set('realWater', real_water)]

    def test_completado_usa_el_agua_real_y_guardar_sin_tocar_no_cambia_nada(self):
        """Caso 6/7: se crea ya completado con 1200 L/ha reales (planificados 1000). Total = 0,5 × 4,2 × 1200 / 1000 = 2,52 L."""
        t = self.new_spraying(self.pL1000, dose='0,5', extra=self.done_steps())
        self.assertEqual(t.status, Treatment.STATUS_COMPLETED)
        self.assertEqual(t.real_water_per_ha, Decimal('1200'))
        self.assert_db(t, dose='0.5', total='2.52', override=False, unit_price='10.00', total_price='25.20', per_ha='6.00', context='completado')
        view = self.reopen_and_check(t, 'completado con agua real')
        self.assertEqual(view['realWater'], '1200')

    def test_marcar_como_hecho_al_editar_recalcula_con_el_agua_real(self):
        """Caso 7: pendiente (2,1 L con 1000 L/ha) → se marca hecho con 1200 L/ha reales → 2,52 L y el estado pasa a completado."""
        t = self.new_spraying(self.pL1000, dose='0,5')
        self.assert_db(t, dose='0.5', total='2.1', override=False, unit_price='10.00', total_price='21.00', per_ha='5.00', context='pendiente')
        t, _ = self.type_and_save_edit(t, self.done_steps())
        self.assertEqual(t.status, Treatment.STATUS_COMPLETED)
        self.assert_db(t, dose='0.5', total='2.52', override=False, unit_price='10.00', total_price='25.20', per_ha='6.00', context='hecho')
        self.reopen_and_check(t, 'marcado como hecho')

    def test_completado_con_total_manual_y_otra_agua_real_respeta_el_total(self):
        """Caso 6 (D1): completado con total a mano 25 y agua real 1200 → dosis 25 × 1000 / 5040 = 4,9603. Si luego el agua
        real pasa a 1000, el total sigue siendo 25 y la dosis se rederiva a 5,9524."""
        t = self.new_spraying(self.pL1000, total='25', extra=self.done_steps())
        self.assert_db(t, dose='4.9603', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='completado manual')
        self.reopen_and_check(t, 'completado con manual')
        t, _ = self.type_and_save_edit(t, [S_set('realWater', 1000)])
        self.assert_db(t, dose='5.9524', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='agua real 1000')
        self.reopen_and_check(t, 'completado agua real 1000')


class Caso8UltimoToqueGanaTests(UseCaseBase):
    def test_total_y_luego_dosis_en_la_misma_sesion(self):
        """Caso 8: se teclea el total 25 y después la dosis 0,6 → gana la dosis: total = 2,52 y sin «a mano»."""
        t = self.new_spraying(self.pL1000, total='25', extra=[S_dose(1, '0,6')])
        self.assert_db(t, dose='0.6', total='2.52', override=False, unit_price='10.00', total_price='25.20', per_ha='6.00', context='total→dosis')
        self.reopen_and_check(t, 'total→dosis')

    def test_dosis_y_luego_total_en_la_misma_sesion(self):
        """Caso 8: dosis 0,6 y después total 25 → gana el total (override)."""
        t = self.new_spraying(self.pL1000, dose='0,6', total='25')
        self.assert_db(t, dose='5.9524', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='dosis→total')
        self.reopen_and_check(t, 'dosis→total')

    def test_vaciar_el_total_recalcula_desde_la_dosis(self):
        """Caso 8: con total 25 guardado (dosis 5,9524) se vacía el total → la dosis (5,9524 → 5,953 hacia arriba)
        manda: 5,953 × 4200 / 1000 = 25,0026 L; coste 250,026 → 250,03; €/ha 250,03 / 4,2 = 59,5310 → 59,53."""
        t = self.new_spraying(self.pL1000, total='25')
        t, _ = self.type_and_save_edit(t, [S_total(1, '')])
        self.assert_db(t, dose='5.953', total='25.0026', override=False, unit_price='10.00', total_price='250.03', per_ha='59.53', context='total vaciado')
        self.reopen_and_check(t, 'total vaciado')

    def test_boton_volver_a_calcular_quita_el_manual(self):
        """Caso 8: «Volver a calcularlo» equivale a vaciar el total y deja la dosis derivada (5,953 tras redondear hacia arriba)."""
        t = self.new_spraying(self.pL1000, total='25')
        t, _ = self.type_and_save_edit(t, [S_clear_total(1)])
        self.assert_db(t, dose='5.953', total='25.0026', override=False, unit_price='10.00', total_price='250.03', per_ha='59.53', context='volver a calcular')
        self.reopen_and_check(t, 'volver a calcular')


class Caso9DosProductosTests(UseCaseBase):
    def two_products(self):
        return self.new_spraying(self.pL1000, total='25', extra=[S_product(self.pKg1000.pk), S_dose(2, '4')])

    def test_un_total_y_una_dosis_con_posiciones_estables(self):
        """Caso 9: línea 1 con total 25 (a mano) y línea 2 con dosis 4 kg/1000L (4 × 4200 / 1000 = 16,8 kg; 16,8 × 9,50 = 159,60 €;
        159,60 / 4,2 = 38,00 €/ha). El orden se mantiene al reabrir y al guardar."""
        t = self.two_products()
        self.assert_db(t, 1, dose='5.9524', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='alta')
        self.assert_db(t, 2, dose='4', total='16.8', override=False, unit_price='9.50', total_price='159.60', per_ha='38.00', context='alta')
        self.assertEqual([tp.product_id for tp in t.treatmentproduct_set.order_by('position')], [self.pL1000.pk, self.pKg1000.pk])
        view = self.reopen_and_check(t, 'dos productos')
        self.assertEqual([l['name'] for l in view['lines']], [self.pL1000.name, self.pKg1000.name])
        self.assertEqual(view['sumMain'], eur('409.60'), 'suma en pantalla = 250,00 + 159,60')

    def test_editar_el_otro_producto_no_toca_el_primero(self):
        """Caso 9: se cambia solo la dosis de la línea 2 a 5 (5 × 4,2 = 21 kg; 199,50 €; 47,50 €/ha); la línea 1 sigue con su 25."""
        t = self.two_products()
        t, _ = self.type_and_save_edit(t, [S_dose(2, '5')])
        self.assert_db(t, 1, dose='5.9524', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='línea 1')
        self.assert_db(t, 2, dose='5', total='21', override=False, unit_price='9.50', total_price='199.50', per_ha='47.50', context='línea 2')
        self.reopen_and_check(t, 'editar línea 2')

    def test_quitar_y_volver_a_poner_un_producto_en_edicion(self):
        """Caso 9: se quita la línea 1 y se vuelve a añadir → pasa a ser la línea 2 con su dosis recomendada (0,5 → 2,1 L, 21,00 €),
        sin total a mano, y el precio congelado de la línea original no se pierde."""
        t = self.two_products()
        t, _ = self.type_and_save_edit(t, [S_remove(1), S_product(self.pL1000.pk)])
        self.assertEqual([tp.product_id for tp in t.treatmentproduct_set.order_by('position')], [self.pKg1000.pk, self.pL1000.pk])
        self.assert_db(t, 1, dose='4', total='16.8', override=False, unit_price='9.50', total_price='159.60', per_ha='38.00', context='línea 1')
        self.assert_db(t, 2, dose='0.5', total='2.1', override=False, unit_price='10.00', total_price='21.00', per_ha='5.00', context='línea 2')
        self.reopen_and_check(t, 'quitar y re-añadir')

    def test_anadir_un_producto_nuevo_en_edicion(self):
        """Caso 9: se añade Abono foliar kg/ha (3 kg/ha × 4,2 = 12,6 kg; × 1,80 = 22,68 €; 5,40 €/ha) en una edición."""
        t = self.new_spraying(self.pL1000, total='25')
        t, _ = self.type_and_save_edit(t, [S_product(self.pKgHa.pk)])
        self.assert_db(t, 1, dose='5.9524', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='línea 1')
        self.assert_db(t, 2, dose='3', total='12.6', override=False, unit_price='1.80', total_price='22.68', per_ha='5.40', context='línea 2')
        self.reopen_and_check(t, 'añadir en edición')


class Caso10VariasParcelasTests(UseCaseBase):
    def test_totales_por_parcela_suma_en_pantalla_igual_a_la_base_de_datos(self):
        """Caso 10: 0,5 L/1000L con 1000 L/ha en A (4,2 ha), B (2,8) y C (6,5) → 3 tratamientos. Totales exactos por parcela:
        0,5 × 4,2 = 2,1 L (21,00 €); 0,5 × 2,8 = 1,4 L (14,00 €); 0,5 × 6,5 = 3,25 L (32,50 €). Suma en pantalla = 67,50 €.
        El total a mano no se puede editar con varias parcelas."""
        steps = [S_type('spraying'), S_set('name', 'Varias'), S_set('water', 1000),
                 S_fields(self.fA.pk, self.fB.pk, self.fC.pk), S_machine(self.m2000.pk), S_product(self.pL1000.pk)]
        view, post, prevented = self.play(self.open_create(), steps + [SUBMIT])
        self.assertFalse(prevented, view['errors'])
        self.assertTrue(view['lines'][0]['totalDisabled'], 'con varias parcelas el total no es editable')
        self.assertEqual(view['lines'][0]['total'], '6,75', 'total en pantalla = 2,1 + 1,4 + 3,25')
        self.assertEqual(view['sumMain'], eur('67.50'))
        before = set(Treatment.objects.values_list('pk', flat=True))
        self.assertEqual(self.client.post(self.create_url, post).status_code, 302)
        created = list(Treatment.objects.exclude(pk__in=before).order_by('field__name'))
        self.assertEqual(len(created), 3)
        want = {self.fA.pk: ('2.1', '21.00'), self.fB.pk: ('1.4', '14.00'), self.fC.pk: ('3.25', '32.50')}
        for t in created:
            total, price = want[t.field_id]
            self.assert_db(t, dose='0.5', total=total, override=False, unit_price='10.00', total_price=price, per_ha='5.00', context=t.field.name)
        self.assertEqual(sum(self.line(t).total_price for t in created), Decimal('67.50'))
        for t in created:      # cada tratamiento se abre y se guarda por separado
            self.reopen_and_check(t, f'abrir {t.field.name}')


class Caso11TratamientoParcialTests(UseCaseBase):
    def test_superficie_parcial_usa_el_area_efectiva_en_dosis_por_1000l(self):
        """Caso 11: 2 ha de las 4,2. 0,5 L/1000L × 2 ha × 1000 L/ha / 1000 = 1 L; 10,00 €; 5,00 €/ha."""
        t = self.new_spraying(self.pL1000, dose='0,5', extra=[S_partial('2')])
        self.assertEqual(t.applied_area, Decimal('2'))
        self.assert_db(t, dose='0.5', total='1', override=False, unit_price='10.00', total_price='10.00', per_ha='5.00', context='parcial')
        self.reopen_and_check(t, 'parcial L/1000L')

    def test_superficie_parcial_en_dosis_por_hectarea(self):
        """Caso 11: 3 kg/ha × 2 ha = 6 kg; × 1,80 = 10,80 €; 10,80 / 2 = 5,40 €/ha."""
        t = self.new_spraying(self.pKgHa, extra=[S_partial('2')])
        self.assert_db(t, dose='3', total='6', override=False, unit_price='1.80', total_price='10.80', per_ha='5.40', context='parcial')
        self.reopen_and_check(t, 'parcial kg/ha')

    def test_superficie_parcial_con_zona_y_cambio_de_area_en_edicion(self):
        """Caso 11: se cambia el área parcial de 2 a 3,5 ha en la edición → 0,5 × 3,5 = 1,75 L; 17,50 €; 5,00 €/ha."""
        t = self.new_spraying(self.pL1000, dose='0,5', extra=[S_partial('2'), S_set('zone', 'Parte alta')])
        t, _ = self.type_and_save_edit(t, [S_partial('3,5')])
        self.assertEqual((t.applied_area, t.zone_notes), (Decimal('3.5'), 'Parte alta'))
        self.assert_db(t, dose='0.5', total='1.75', override=False, unit_price='10.00', total_price='17.50', per_ha='5.00', context='3,5 ha')
        self.reopen_and_check(t, 'parcial 3,5')


class Caso12PrecioCongeladoTests(UseCaseBase):
    """Regla del producto (Product.save): al cambiar su precio se actualizan los tratamientos NO completados; los completados
    conservan el precio con el que se hicieron. El formulario enseña siempre el precio guardado en la línea (E4)."""

    def change_price(self, new):
        self.pL1000.price = Decimal(new)
        self.pL1000.save()

    def test_pendiente_enseña_el_precio_guardado_tras_el_cambio_de_precio(self):
        """Caso 12: el producto sube de 10 a 12 €. El pendiente se actualiza: 2,1 L × 12 = 25,20 €; 25,20 / 4,2 = 6,00 €/ha.
        La pantalla enseña lo guardado y guardar sin tocar no lo cambia."""
        t = self.new_spraying(self.pL1000, dose='0,5')
        self.change_price('12.00')
        self.assert_db(t, dose='0.5', total='2.1', override=False, unit_price='12.00', total_price='25.20', per_ha='6.00', context='tras subir el precio')
        view = self.reopen_and_check(t, 'precio sube, pendiente')
        self.assertEqual(view['lines'][0]['cost'], eur('25.20'))

    def test_pendiente_editar_dosis_usa_el_precio_guardado(self):
        """Caso 12: tras la subida, editar la dosis a 0,6 → 2,52 L × 12 = 30,24 €; 30,24 / 4,2 = 7,20 €/ha (el mismo que enseña la pantalla)."""
        t = self.new_spraying(self.pL1000, dose='0,5')
        self.change_price('12.00')
        t, view = self.type_and_save_edit(t, [S_dose(1, '0,6')])
        self.assertEqual(view['lines'][0]['cost'], eur('30.24'), 'coste en pantalla antes de guardar')
        self.assert_db(t, dose='0.6', total='2.52', override=False, unit_price='12.00', total_price='30.24', per_ha='7.20', context='dosis con precio nuevo')
        self.reopen_and_check(t, 'precio sube, editar dosis')

    def test_completado_conserva_el_precio_con_el_que_se_hizo(self):
        """Caso 12 (E4): completado (2,52 L con 1200 L/ha reales) × 10 € = 25,20 €, aunque el producto cueste ya 12 €.
        La pantalla enseña 25,20 € y guardar sin tocar no lo cambia; editar la dosis a 0,6 da 3,024 L × 10 = 30,24 €."""
        t = self.new_spraying(self.pL1000, dose='0,5', extra=[S_done(True), S_set('finish', '2026-10-26'), S_set('realWater', 1200)])
        self.change_price('12.00')
        self.assert_db(t, dose='0.5', total='2.52', override=False, unit_price='10.00', total_price='25.20', per_ha='6.00', context='completado')
        view = self.reopen_and_check(t, 'precio sube, completado')
        self.assertEqual(view['lines'][0]['cost'], eur('25.20'))
        t, _ = self.type_and_save_edit(t, [S_dose(1, '0,6')])
        # 0,6 × 4,2 × 1200 / 1000 = 3,024 L; × 10 = 30,24 €; / 4,2 = 7,20 €/ha
        self.assert_db(t, dose='0.6', total='3.024', override=False, unit_price='10.00', total_price='30.24', per_ha='7.20', context='completado editado')
        self.reopen_and_check(t, 'completado editado')

    def test_producto_quitado_y_vuelto_a_poner_conserva_el_precio_de_la_linea(self):
        """Caso 12: quitar y volver a añadir un producto ya guardado conserva el precio de su línea (12 € tras la subida,
        2,1 × 12 = 25,20 €); uno nuevo (Abono foliar kg/ha) entra con el precio actual del producto (1,80 €)."""
        t = self.new_spraying(self.pL1000, dose='0,5')
        self.change_price('12.00')
        t, _ = self.type_and_save_edit(t, [S_remove(1), S_product(self.pL1000.pk), S_product(self.pKgHa.pk)])
        self.assert_db(t, 1, dose='0.5', total='2.1', override=False, unit_price='12.00', total_price='25.20', per_ha='6.00', context='re-añadido')
        self.assert_db(t, 2, dose='3', total='12.6', override=False, unit_price='1.80', total_price='22.68', per_ha='5.40', context='nuevo')
        self.reopen_and_check(t, 'quitar y re-añadir tras subida')


class Caso13ErrorDelServidorTests(UseCaseBase):
    """El servidor rechaza el formulario (el JS no lo detecta): vuelve con lo tecleado, sin perder el total a mano, y se corrige."""

    @staticmethod
    def water_key(post):
        return next(k for k in post if 'water' in k and 'real' not in k)

    def test_alta_con_error_en_el_agua_conserva_el_total_manual_y_se_corrige(self):
        """Caso 13: total a mano 25 y agua -5 (el servidor la rechaza). La pantalla vuelve con 25 «a mano» y sin crear nada;
        se corrige el agua a 1000 y se guarda: dosis 5,9524, total 25, 250,00 €."""
        steps = [S_type('spraying'), S_set('name', 'Con error'), S_set('water', 1000), S_fields(self.fA.pk),
                 S_machine(self.m2000.pk), S_product(self.pL1000.pk), S_total(1, '25')]
        view, post, prevented = self.play(self.open_create(), steps + [SUBMIT])
        self.assertFalse(prevented)
        bad = dict(post, **{self.water_key(post): '-5'})
        before = Treatment.objects.count()
        response = self.client.post(self.create_url, bad)
        self.assertEqual(response.status_code, 200, 'debe volver al formulario')
        self.assertEqual(Treatment.objects.count(), before, 'no se guarda nada si hay error')
        back, post2, prevented = self.play(response.content.decode(), [SUBMIT])
        self.assertEqual((back['name'], back['lines'][0]['total'], back['lines'][0]['manual']), ('Con error', '25', True),
                         f'tecleado=25, mostrado al volver={back["lines"][0]["total"]}')
        self.assertTrue(prevented, 'sin agua válida el JS no deja enviar')
        back, post2, prevented = self.play(response.content.decode(), [S_set('water', 1000), SUBMIT])
        self.assertFalse(prevented, back['errors'])
        self.assertEqual(back['lines'][0]['total'], '25')
        self.assertEqual(self.client.post(self.create_url, post2).status_code, 302)
        t = Treatment.objects.order_by('-pk').first()
        self.assert_db(t, dose='5.9524', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='corregido')
        self.reopen_and_check(t, 'alta corregida')

    def test_edicion_con_error_conserva_lo_tecleado_y_se_corrige(self):
        """Caso 13 (edición): se edita el total a 30 y el servidor rechaza el agua (-5). Al volver sigue el 30 «a mano»;
        se corrige el agua a 1200 y queda: dosis 30 × 1000 / 5040 = 5,9524, total 30, 300,00 €; 300 / 4,2 = 71,43 €/ha."""
        t = self.new_spraying(self.pL1000, total='25')
        view, post, prevented = self.play(self.open_edit(t), [S_total(1, '30'), SUBMIT])
        self.assertFalse(prevented)
        response = self.client.post(self.edit_url(t), dict(post, **{self.water_key(post): '-5'}))
        self.assertEqual(response.status_code, 200)
        self.assert_db(t, dose='5.9524', total='25', override=True, unit_price='10.00', total_price='250.00', per_ha='59.52', context='sin cambios tras el error')
        back, post2, prevented = self.play(response.content.decode(), [S_set('water', 1200), SUBMIT])
        self.assertFalse(prevented, back['errors'])
        self.assertEqual((back['lines'][0]['total'], back['lines'][0]['manual']), ('30', True))
        self.assertEqual(self.client.post(self.edit_url(t), post2).status_code, 302)
        self.assert_db(t, dose='5.9524', total='30', override=True, unit_price='10.00', total_price='300.00', per_ha='71.43', context='corregido')
        self.reopen_and_check(t, 'edición corregida')


class Caso14TextoTecleadoTests(UseCaseBase):
    """Lo que teclea el usuario (coma, punto, espacios, muchos decimales): qué se guarda y qué se enseña al volver."""

    def check_dose(self, typed, dose, total, price, per_ha, shown_dose):
        t = self.new_spraying(self.pL1000, dose=typed)
        self.assert_db(t, dose=dose, total=total, override=False, unit_price='10.00', total_price=price, per_ha=per_ha, context=f'tecleado={typed!r}')
        view = self.reopen_and_check(t, f'tecleado={typed!r}')
        self.assertEqual(view['lines'][0]['dose'], shown_dose, f'tecleado={typed!r}, guardado={self.line(t).dose}, mostrado={view["lines"][0]["dose"]}')

    def check_total(self, typed, dose, total, price, per_ha, shown_total):
        t = self.new_spraying(self.pL1000, total=typed)
        self.assert_db(t, dose=dose, total=total, override=True, unit_price='10.00', total_price=price, per_ha=per_ha, context=f'tecleado={typed!r}')
        view = self.reopen_and_check(t, f'tecleado={typed!r}')
        self.assertEqual(view['lines'][0]['total'], shown_total, f'tecleado={typed!r}, guardado={self.line(t).total_dose}, mostrado={view["lines"][0]["total"]}')

    def test_dosis_con_coma_punto_y_espacios(self):
        """Caso 14: «0,5», «0.5» y « 0,5 » son la misma dosis: 0,5 × 4,2 = 2,1 L; 21,00 €; 5,00 €/ha."""
        for typed in ('0,5', '0.5', ' 0,5 '):
            with self.subTest(typed=typed):
                self.check_dose(typed, '0.5', '2.1', '21.00', '5.00', '0,5')

    def test_dosis_de_tres_decimales(self):
        """Caso 14: 1,125 × 4,2 = 4,725 L; 47,25 €; 47,25 / 4,2 = 11,25 €/ha."""
        self.check_dose('1,125', '1.125', '4.725', '47.25', '11.25', '1,125')

    def test_dosis_de_cuatro_decimales_se_redondea_hacia_arriba_a_tres(self):
        """Caso 14 (clean_dose ROUND_UP): 1,1255 → 1,126; 1,126 × 4,2 = 4,7292 L; 47,292 → 47,29 €; 47,29 / 4,2 = 11,2595 → 11,26 €/ha.
        El formulario avisa del redondeo y enseña 1,126 al volver."""
        self.check_dose('1,1255', '1.126', '4.7292', '47.29', '11.26', '1,126')

    def test_total_con_muchos_decimales_se_redondea_a_cuatro(self):
        """Caso 14: 24,999999 → 25,0000 (a 4 decimales, sin ruido): dosis 25 / 4,2 = 5,9524; 250,00 €; 59,52 €/ha. Se enseña «25»."""
        self.check_total('24,999999', '5.9524', '25', '250.00', '59.52', '25')

    def test_total_con_cinco_decimales_que_no_llegan_a_redondear_a_entero(self):
        """Caso 14: 24,99994 → 24,9999; dosis 24,9999 / 4,2 = 5,95235714 → 5,9524; 249,999 → 250,00 €; 59,52 €/ha."""
        self.check_total('24,99994', '5.9524', '24.9999', '250.00', '59.52', '24,9999')

    def test_total_con_punto_decimal_y_con_espacios(self):
        """Caso 14: «24.5» y « 30 »: 24,5 → dosis 5,8333, 245,00 €, 58,33 €/ha; 30 → dosis 7,1429, 300,00 €, 71,43 €/ha."""
        self.check_total('24.5', '5.8333', '24.5', '245.00', '58.33', '24,5')
        self.check_total(' 30 ', '7.1429', '30', '300.00', '71.43', '30')

    def test_punto_de_miles_ambiguo_se_rechaza_con_aviso(self):
        """Caso 14: «1.500» (¿uno y medio o mil quinientos?) no se guarda: el formulario pide usar la coma."""
        for kind, step in (('dosis', S_dose(1, '1.500')), ('total', S_total(1, '1.500'))):
            with self.subTest(campo=kind):
                steps = [S_type('spraying'), S_set('name', 'Ambiguo'), S_set('water', 1000), S_fields(self.fA.pk),
                         S_machine(self.m2000.pk), S_product(self.pL1000.pk), step]
                view, post, prevented = self.play(self.open_create(), steps + [SUBMIT, {'op': 'snap'}])
                self.assertTrue(prevented, f'tecleado=1.500 en {kind}: no debería dejar guardar')
                texts = ' '.join([view['missing'] or '', view['save'] or '', view['lines'][0]['notes']] + [m or '' for _, m in view['errors']])
                self.assertIn('Usa coma', texts, f'sin aviso de usar coma: missing={view["missing"]!r}, errores={view["errors"]}')
