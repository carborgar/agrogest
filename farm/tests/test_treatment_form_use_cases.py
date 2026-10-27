"""
Casos de uso completos del formulario de tratamiento (ver farm/tests/form_cycle.py para el método).

Cada test: teclear en el formulario real (JS real en jsdom) → POST real → base de datos contra valores calculados a mano
→ reabrir la edición y comparar el TEXTO mostrado → guardar sin tocar nada 3 veces y exigir base de datos idéntica.
Escenario base: parcela A de 4,2 ha, cuba de 2000 L, 1000 L de agua/ha → 4200 L de caldo; B = 2,8 ha; C = 6,5 ha.
"""
from decimal import Decimal

from farm.models import Treatment
from farm.tests.form_cycle import (S_date, S_done, S_dose, S_fields, S_machine, S_partial, S_product, S_remove, S_set,
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
