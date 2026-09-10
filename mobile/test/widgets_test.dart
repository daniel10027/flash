import 'package:flash_app/shared/format/money_format.dart';
import 'package:flash_app/shared/widgets/amount_field.dart';
import 'package:flash_app/shared/widgets/money_text.dart';
import 'package:flash_app/shared/widgets/pin_pad.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _wrap(Widget child) =>
    MaterialApp(home: Scaffold(body: Center(child: child)));

void main() {
  test('formatMoney : XOF sans décimale, EUR avec centimes', () {
    expect(formatMoney(125000, 'XOF').replaceAll(RegExp(r'\D'), ''), '125000');
    expect(formatMoney(1500, 'EUR'), contains('15'));
    expect(minorToMajor(1500, 'EUR'), 15);
    expect(minorToMajor(1500, 'XOF'), 1500);
  });

  testWidgets('AmountField : montant XOF + frais 0,8 %', (tester) async {
    var value = 0;
    await tester.pumpWidget(
      _wrap(
        StatefulBuilder(
          builder: (context, setState) => AmountField(
            currency: 'XOF',
            valueMinor: value,
            showFee: true,
            onChanged: (v) => setState(() => value = v),
          ),
        ),
      ),
    );
    await tester.enterText(find.byType(TextField), '10000');
    await tester.pump();
    expect(value, 10000);
    expect(find.text('Frais (0,8 %)'), findsOneWidget);
    // total = 10000 + ceil(10000*80/10000)=80 -> 10 080
    expect(
      find.byWidgetPredicate(
        (w) =>
            w is Text &&
            (w.data ?? '').replaceAll(RegExp(r'\D'), '') == '10080',
      ),
      findsOneWidget,
    );
  });

  testWidgets('MoneyText masqué affiche des points', (tester) async {
    await tester.pumpWidget(_wrap(const MoneyText(5000, 'XOF', hidden: true)));
    expect(find.text('••••••'), findsOneWidget);
  });

  testWidgets('PinPad : saisie et complétion', (tester) async {
    var value = '';
    String? completed;
    await tester.pumpWidget(
      _wrap(
        StatefulBuilder(
          builder: (context, setState) => PinPad(
            length: 4,
            value: value,
            onChanged: (v) => setState(() => value = v),
            onCompleted: (v) => completed = v,
          ),
        ),
      ),
    );
    for (final d in ['2', '4', '6', '8']) {
      await tester.tap(find.text(d));
      await tester.pump();
    }
    expect(value, '2468');
    expect(completed, '2468');
  });
}
