import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/network/api_client.dart';
import '../../l10n/generated/app_localizations.dart';
import '../../shared/widgets/common.dart';
import '../../shared/widgets/money_text.dart';
import '../wallet/wallet_models.dart';
import 'op_detail_sheet.dart';

/// Historique paginé (`GET /v1/statement`), regroupé par jour, scroll infini.
class HistoryPage extends ConsumerStatefulWidget {
  const HistoryPage({super.key});

  @override
  ConsumerState<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends ConsumerState<HistoryPage> {
  final _scroll = ScrollController();
  final _items = <StatementLine>[];
  String? _cursor;
  bool _loading = false;
  bool _done = false;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      if (_scroll.position.pixels > _scroll.position.maxScrollExtent - 400) {
        _load();
      }
    });
    _load();
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (_loading || _done) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final r = await ref.read(apiClientProvider).getJson(
        '/v1/statement',
        query: {'limit': 25, if (_cursor != null) 'cursor': _cursor},
      );
      final lines = ((r['lines'] as List?) ?? const [])
          .map((e) => StatementLine.fromJson(e as Map<String, dynamic>))
          .toList();
      setState(() {
        _items.addAll(lines);
        _cursor = r['next_cursor'] as String?;
        _done = _cursor == null || lines.isEmpty;
      });
    } catch (e) {
      setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _refresh() async {
    setState(() {
      _items.clear();
      _cursor = null;
      _done = false;
    });
    await _load();
  }

  Map<String, List<StatementLine>> get _grouped {
    final fmt = DateFormat.yMMMMEEEEd('fr');
    final out = <String, List<StatementLine>>{};
    for (final l in _items) {
      out.putIfAbsent(fmt.format(l.occurredAt), () => []).add(l);
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);

    if (_items.isEmpty && _error != null) {
      return Scaffold(
        appBar: AppBar(title: Text(l.navHistory)),
        body: EmptyState(
          icon: Icons.wifi_off,
          title: l.errorGeneric,
          action: TextButton(onPressed: _load, child: Text(l.actionRetry)),
        ),
      );
    }
    if (_items.isEmpty && _loading) {
      return Scaffold(
        appBar: AppBar(title: Text(l.navHistory)),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: List.generate(
            8,
            (_) => const Padding(
              padding: EdgeInsets.symmetric(vertical: 10),
              child: Skeleton(height: 44),
            ),
          ),
        ),
      );
    }
    if (_items.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: Text(l.navHistory)),
        body: const EmptyState(
          icon: Icons.history,
          title: 'Aucune opération',
          message: 'Vos transferts et paiements apparaîtront ici.',
        ),
      );
    }

    final groups = _grouped;
    return Scaffold(
      appBar: AppBar(title: Text(l.navHistory)),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView.builder(
          controller: _scroll,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          itemCount: groups.length + 1,
          itemBuilder: (context, i) {
            if (i == groups.length) {
              return Padding(
                padding: const EdgeInsets.all(16),
                child: Center(
                  child: _done
                      ? Text(
                          '— fin —',
                          style: TextStyle(color: Theme.of(context).hintColor),
                        )
                      : const CircularProgressIndicator(),
                ),
              );
            }
            final day = groups.keys.elementAt(i);
            final lines = groups[day]!;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(4, 16, 4, 4),
                  child: Text(
                    day,
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                          color: Theme.of(context).hintColor,
                        ),
                  ),
                ),
                for (final op in lines)
                  ListRow(
                    leading: CircleAvatar(
                      backgroundColor:
                          Theme.of(context).colorScheme.surfaceContainerHighest,
                      child: Icon(
                        op.direction == 'in'
                            ? Icons.south_west
                            : Icons.north_east,
                        size: 18,
                      ),
                    ),
                    title: op.counterparty ?? op.kind,
                    subtitle:
                        '${op.reference} · ${DateFormat.Hm().format(op.occurredAt)}',
                    trailing: MoneyText(
                      op.signedMinor,
                      op.currency,
                      withSign: true,
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    onTap: op.reference.isEmpty
                        ? null
                        : () => showOpDetail(context, op.reference),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }
}
