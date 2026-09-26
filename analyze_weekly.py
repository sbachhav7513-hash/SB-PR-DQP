#!/usr/bin/env python3
"""
Weekly Analysis Tool - Run every Friday to generate metrics
Usage: python analyze_weekly.py [days=7]
"""

import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from zoneinfo import ZoneInfo

from market_bot.trade_journal import PaperTradingRecorder, normalize_decision_outcome


IST = ZoneInfo('Asia/Kolkata')


def parse_timestamp(value):
    """Parse journal timestamps as UTC when they do not include a timezone."""
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_paper_records(parquet_name, days, columns):
    paper_root = Path('paper_trading_data')
    paths = sorted(paper_root.glob(f'*/*/day_*/{parquet_name}'))
    if not paths:
        return None

    valid_records = []
    for path in paths:
        try:
            rows = PaperTradingRecorder._read_parquet(path, columns=columns)
        except Exception:
            try:
                rows = PaperTradingRecorder._read_parquet(path)
            except Exception as error:
                print(f'⚠️  Could not read {path}: {error}')
                continue
        for record in rows:
            timestamp = parse_timestamp(record.get('timestamp', ''))
            if timestamp is not None:
                valid_records.append((timestamp, record))

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    recent = [record for timestamp, record in valid_records if timestamp > cutoff_date]
    if recent:
        return recent
    if not valid_records:
        return []
    fallback_cutoff = max(timestamp for timestamp, _ in valid_records) - timedelta(days=days)
    return [
        record for timestamp, record in valid_records
        if timestamp >= fallback_cutoff
    ]

def load_trades(days=7):
    """Load trades from the past N days"""
    paper_trades = load_paper_records(
        'trades.parquet', days, ['timestamp', 'ticker', 'action', 'status', 'pnl']
    )
    if paper_trades is not None:
        return [trade for trade in paper_trades if trade.get('status') == 'closed']

    trades = []
    trades_file = Path('trades.jsonl')
    
    if not trades_file.exists():
        print("❌ ERROR: trades.jsonl not found!")
        print("   Make sure the bot has run and created trades.jsonl")
        return []
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    try:
        with open(trades_file, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        trade = json.loads(line)
                        trade_time = parse_timestamp(trade.get('timestamp', ''))
                        
                        if trade_time and trade_time > cutoff_date and trade.get('status') == 'closed':
                            trades.append(trade)
                    except (json.JSONDecodeError, ValueError) as e:
                        continue
    except Exception as e:
        print(f"❌ Error reading trades.jsonl: {e}")
        return []
    
    return trades

def load_decisions(days=7):
    """Load strategy decisions and their analyzed market windows."""
    paper_decisions = load_paper_records(
        'decisions.parquet', days, [
            'timestamp', 'ticker', 'signal', 'outcome', 'outcome_detail',
            'rejection_reason', 'market_session', 'market_hours', 'session_timezone',
        ]
    )
    if paper_decisions is not None:
        return paper_decisions

    decisions = []
    decision_file = Path('decision_log.jsonl')
    if not decision_file.exists():
        print("⚠️  Note: decision_log.jsonl not found yet (restart the bot after this update)")
        return decisions

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        with open(decision_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    decision = json.loads(line)
                    decision_time = parse_timestamp(decision.get('timestamp', ''))
                    if decision_time and decision_time > cutoff_date:
                        decisions.append(decision)
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError as e:
        print(f"⚠️  Could not read decision_log.jsonl: {e}")
    return decisions

def iter_decisions(days=7):
    """Yield recent decisions one at a time to keep analysis memory bounded."""
    paper_decisions = load_paper_records(
        'decisions.parquet', days, [
            'timestamp', 'ticker', 'signal', 'outcome', 'outcome_detail',
            'rejection_reason', 'market_session', 'market_hours', 'session_timezone',
        ]
    )
    if paper_decisions is not None:
        yield from paper_decisions
        return

    decision_file = Path('decision_log.jsonl')
    if not decision_file.exists():
        print("⚠️  Note: decision_log.jsonl not found yet (restart the bot after this update)")
        return

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        with decision_file.open('r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    decision = json.loads(line)
                    decision_time = parse_timestamp(decision.get('timestamp', ''))
                    if decision_time and decision_time > cutoff_date:
                        yield decision
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError as e:
        print(f"⚠️  Could not read decision_log.jsonl: {e}")

def analyze_decisions(decisions):
    """Summarize what the strategy evaluated, rejected, and attempted."""
    signal_counts = defaultdict(int)
    outcome_counts = defaultdict(int)
    market_session_counts = defaultdict(int)
    symbol_counts = defaultdict(lambda: {'bars': 0, 'buy': 0, 'sell': 0, 'hold': 0})
    total_decisions = 0

    for decision in decisions:
        total_decisions += 1
        signal = decision.get('signal', 'UNKNOWN')
        symbol = decision.get('ticker', 'UNKNOWN')
        signal_counts[signal] += 1
        outcome_counts[normalize_decision_outcome(decision.get('outcome', 'UNKNOWN'))] += 1
        session = decision.get('market_session')
        if not session:
            timestamp = parse_timestamp(decision.get('timestamp', ''))
            session = 'unknown'
            if timestamp:
                local_time = timestamp.astimezone(IST).time()
                session = (
                    'regular_session' if time(9, 15) <= local_time < time(15, 30)
                    else 'before_open' if local_time < time(9, 15)
                    else 'after_close'
                )
        market_session_counts[str(session)] += 1
        symbol_counts[symbol]['bars'] += 1
        if signal == 'BUY':
            symbol_counts[symbol]['buy'] += 1
        elif signal == 'SELL':
            symbol_counts[symbol]['sell'] += 1
        elif signal == 'HOLD':
            symbol_counts[symbol]['hold'] += 1

    rejected = sum(
        outcome_counts[name]
        for name in ('accuracy_filter', 'option_filter', 'risk_blocked', 'execution_failed')
    )
    approved = outcome_counts['trade_opened']
    non_entry = total_decisions - approved - rejected
    return {
        'total_decisions': total_decisions,
        'session_timezone': IST.key,
        'signal_counts': dict(signal_counts),
        'outcome_counts': dict(outcome_counts),
        'market_session_counts': dict(market_session_counts),
        'decision_reconciliation': {
            'approved_entries': approved,
            'classified_rejections': rejected,
            'non_entry_decisions': non_entry,
            'accounted_decisions': approved + rejected + non_entry,
            'matches_decisions_recorded': approved + rejected + non_entry == total_decisions,
        },
        'symbol_counts': dict(symbol_counts),
    }

def load_filter_stats(days=7, decisions=None):
    """Load filter statistics"""
    stats = {
        'volatility_rejected': 0,
        'confirmation_rejected': 0,
        'cooldown_rejected': 0,
        'hours_rejected': 0,
        'threshold_rejected': 0,
        'approved_entries': 0,
        'option_rejected': 0,
        'risk_rejected': 0,
        'execution_failures': 0,
    }

    if decisions is not None:
        has_decisions = False
        for decision in decisions:
            has_decisions = True
            outcome = str(decision.get('outcome', ''))
            detail = str(decision.get('outcome_detail') or outcome)
            category = normalize_decision_outcome(outcome)
            if category == 'trade_opened':
                stats['approved_entries'] += 1
            elif category == 'accuracy_filter' or detail.startswith('accuracy_filter_rejected:'):
                reason = str(decision.get('rejection_reason', '')) or detail.split(':', 1)[-1]
                if reason == 'volatility':
                    stats['volatility_rejected'] += 1
                elif reason == 'confirmation':
                    stats['confirmation_rejected'] += 1
                elif reason == 'cooldown':
                    stats['cooldown_rejected'] += 1
                elif reason == 'trading_hours':
                    stats['hours_rejected'] += 1
                else:
                    stats['threshold_rejected'] += 1
            elif category == 'option_filter' or detail.startswith('OPTION_FILTER_'):
                stats['option_rejected'] += 1
            elif category == 'risk_blocked':
                stats['risk_rejected'] += 1
            elif category == 'execution_failed':
                stats['execution_failures'] += 1
        if has_decisions:
            stats['total_rejected'] = sum(
                stats[name] for name in (
                    'volatility_rejected', 'confirmation_rejected',
                    'cooldown_rejected', 'hours_rejected', 'threshold_rejected',
                    'option_rejected', 'risk_rejected', 'execution_failures',
                )
            )
            return stats
    
    filter_log = Path('filter_log.jsonl')
    
    if not filter_log.exists():
        print("⚠️  Note: filter_log.jsonl not found yet (will be created after bot runs with updated code)")
        return stats
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    try:
        with open(filter_log, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        entry_time = parse_timestamp(entry.get('timestamp', ''))
                        
                        if entry_time and entry_time > cutoff_date:
                            filter_name = entry.get('filter', '')
                            action = entry.get('action', '')
                            
                            if action == 'REJECTED':
                                if filter_name in stats:
                                    stats[filter_name] += 1
                            elif action == 'APPROVED':
                                stats['approved_entries'] += 1
                    except (json.JSONDecodeError, ValueError):
                        continue
    except Exception as e:
        print(f"⚠️  Could not read filter_log.jsonl: {e}")
    
    return stats

def analyze_trades(trades):
    """Generate analysis metrics"""
    
    if not trades:
        print("❌ ERROR: No trades found in the past 7 days!")
        print("   Run the bot first: python run_kite_bot.py")
        return None
    
    # Basic counts
    total_trades = len(trades)
    profit = lambda trade: float(trade.get('pnl', trade.get('profit', 0)) or 0)
    wins = [t for t in trades if profit(t) > 0]
    losses = [t for t in trades if profit(t) <= 0]
    win_count = len(wins)
    loss_count = len(losses)
    
    # Financial metrics
    total_profit = sum(profit(t) for t in trades)
    win_sum = sum(profit(t) for t in wins) if wins else 0
    loss_sum = sum(profit(t) for t in losses) if losses else 0
    
    avg_win = win_sum / len(wins) if wins else 0
    avg_loss = loss_sum / len(losses) if losses else 0
    profit_factor = win_sum / abs(loss_sum) if loss_sum != 0 else 0
    
    # By symbol
    symbol_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'profit': 0, 'count': 0})
    
    for trade in trades:
        symbol = trade.get('ticker', trade.get('symbol', 'UNKNOWN'))
        trade_profit = profit(trade)
        symbol_stats[symbol]['count'] += 1
        symbol_stats[symbol]['profit'] += trade_profit
        
        if trade_profit > 0:
            symbol_stats[symbol]['wins'] += 1
        else:
            symbol_stats[symbol]['losses'] += 1
    
    # By hour
    hour_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'profit': 0, 'count': 0})
    
    for trade in trades:
        try:
            trade_time = parse_timestamp(trade.get('timestamp', ''))
            if trade_time is None:
                continue
            hour = trade_time.astimezone(IST).hour
            trade_profit = profit(trade)
            
            hour_stats[hour]['count'] += 1
            hour_stats[hour]['profit'] += trade_profit
            
            if trade_profit > 0:
                hour_stats[hour]['wins'] += 1
            else:
                hour_stats[hour]['losses'] += 1
        except:
            continue
    
    return {
        'total_trades': total_trades,
        'win_count': win_count,
        'loss_count': loss_count,
        'win_rate': (win_count / total_trades * 100) if total_trades > 0 else 0,
        'total_profit': total_profit,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'largest_win': max((profit(t) for t in trades), default=0),
        'largest_loss': min((profit(t) for t in trades), default=0),
        'symbol_stats': dict(symbol_stats),
        'hour_stats': dict(hour_stats),
        'trades': trades
    }

def print_report(analysis, filter_stats, decision_analysis):
    """Print formatted report"""
    
    print("\n" + "="*70)
    print("📊 WEEKLY TRADING ANALYSIS REPORT")
    print("="*70)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Analysis Period: Last 7 days")
    print("="*70)
    
    # Performance Summary
    print("\n📈 PERFORMANCE SUMMARY")
    print("-" * 70)
    print(f"Total Trades:        {analysis['total_trades']}")
    print(f"Winning Trades:      {analysis['win_count']} ({analysis['win_rate']:.1f}%)")
    print(f"Losing Trades:       {analysis['loss_count']} ({100-analysis['win_rate']:.1f}%)")
    
    # Profitability
    print("\n💰 PROFITABILITY")
    print("-" * 70)
    print(f"Total Profit/Loss:   ₹{analysis['total_profit']:,.2f}")
    print(f"Average Win:         ₹{analysis['avg_win']:,.2f}")
    print(f"Average Loss:        ₹{analysis['avg_loss']:,.2f}")
    print(f"Largest Win:         ₹{analysis['largest_win']:,.2f}")
    print(f"Largest Loss:        ₹{analysis['largest_loss']:,.2f}")
    print(f"Profit Factor:       {analysis['profit_factor']:.2f}x")

    print("\n🧠 STRATEGY DECISION AUDIT")
    print("-" * 70)
    print(f"Bars analyzed:        {decision_analysis['total_decisions']}")
    print(f"BUY signals:          {decision_analysis['signal_counts'].get('BUY', 0)}")
    print(f"SELL signals:         {decision_analysis['signal_counts'].get('SELL', 0)}")
    print(f"HOLD decisions:       {decision_analysis['signal_counts'].get('HOLD', 0)}")
    print(f"Strategy errors:      {decision_analysis['outcome_counts'].get('strategy_error', 0)}")
    print(f"Trades opened:        {decision_analysis['outcome_counts'].get('trade_opened', 0)}")
    print(f"Skipped:              {decision_analysis['outcome_counts'].get('position_size_zero', 0)}")
    
    # By Symbol
    print("\n📍 PERFORMANCE BY SYMBOL")
    print("-" * 70)
    print(f"{'Symbol':<15} {'Trades':>8} {'Wins':>8} {'Win%':>8} {'Profit':>12}")
    print("-" * 70)
    
    for symbol in sorted(analysis['symbol_stats'].keys()):
        stats = analysis['symbol_stats'][symbol]
        win_pct = (stats['wins'] / stats['count'] * 100) if stats['count'] > 0 else 0
        print(f"{symbol:<15} {stats['count']:>8} {stats['wins']:>8} {win_pct:>7.1f}% ₹{stats['profit']:>10,.2f}")
    
    # By Hour
    print("\n⏰ PERFORMANCE BY HOUR")
    print("-" * 70)
    print(f"{'Hour':<10} {'Trades':>8} {'Wins':>8} {'Win%':>8} {'Profit':>12}")
    print("-" * 70)
    
    for hour in sorted(analysis['hour_stats'].keys()):
        stats = analysis['hour_stats'][hour]
        win_pct = (stats['wins'] / stats['count'] * 100) if stats['count'] > 0 else 0
        time_str = f"{hour:02d}:00-{hour+1:02d}:00"
        print(f"{time_str:<10} {stats['count']:>8} {stats['wins']:>8} {win_pct:>7.1f}% ₹{stats['profit']:>10,.2f}")
    
    # Filter Statistics
    print("\n🔍 FILTER STATISTICS")
    print("-" * 70)
    print(f"Volatility Rejected:      {filter_stats['volatility_rejected']:>6}")
    print(f"Confirmation Rejected:    {filter_stats['confirmation_rejected']:>6}")
    print(f"Cooldown Rejected:        {filter_stats['cooldown_rejected']:>6}")
    print(f"Hours Rejected:           {filter_stats['hours_rejected']:>6}")
    print(f"Threshold Rejected:       {filter_stats['threshold_rejected']:>6}")
    print(f"                         " + "-"*7)
    total_rejected = sum([
        filter_stats['volatility_rejected'],
        filter_stats['confirmation_rejected'],
        filter_stats['cooldown_rejected'],
        filter_stats['hours_rejected'],
        filter_stats['threshold_rejected']
    ])
    print(f"Total Rejected:           {total_rejected:>6}")
    print(f"Approved Entries:         {filter_stats['approved_entries']:>6}")
    
    # Recommendations
    print("\n💡 RECOMMENDATIONS FOR NEXT WEEK")
    print("-" * 70)
    
    # Best performing hour
    if analysis['hour_stats']:
        best_hour = max(analysis['hour_stats'].items(), 
                       key=lambda x: x[1]['profit'])
        print(f"✅ BEST TRADING HOUR: {best_hour[0]:02d}:00-{best_hour[0]+1:02d}:00 (₹{best_hour[1]['profit']:,.2f})")
    
    # Worst performing hour
    if analysis['hour_stats']:
        worst_hour = min(analysis['hour_stats'].items(), 
                        key=lambda x: x[1]['profit'])
        print(f"❌ WORST TRADING HOUR: {worst_hour[0]:02d}:00-{worst_hour[0]+1:02d}:00 (₹{worst_hour[1]['profit']:,.2f})")
    
    # Best performing symbol
    if analysis['symbol_stats']:
        best_symbol = max(analysis['symbol_stats'].items(), 
                         key=lambda x: x[1]['profit'])
        print(f"✅ BEST SYMBOL: {best_symbol[0]} (₹{best_symbol[1]['profit']:,.2f}, {best_symbol[1]['wins']}/{best_symbol[1]['count']} wins)")
    
    # Worst performing symbol
    if analysis['symbol_stats']:
        worst_symbol = min(analysis['symbol_stats'].items(), 
                          key=lambda x: x[1]['profit'])
        print(f"❌ WORST SYMBOL: {worst_symbol[0]} (₹{worst_symbol[1]['profit']:,.2f}, {worst_symbol[1]['wins']}/{worst_symbol[1]['count']} wins)")
    
    # Win rate assessment
    print(f"\n{'Status':<40} {analysis['win_rate']:>6.1f}%")
    if analysis['win_rate'] >= 70:
        print("✅ EXCELLENT - Keep current strategy")
    elif analysis['win_rate'] >= 60:
        print("✅ GOOD - Minor tweaks may help")
    elif analysis['win_rate'] >= 55:
        print("⚠️  MARGINAL - Implement improvements")
    else:
        print("❌ POOR - Major changes needed")
    
    print("\n" + "="*70)
    print("📋 NEXT STEPS:")
    print("  1. Review this report")
    print("  2. Open weekly_input_template.json")
    print("  3. Fill in your observations")
    print("  4. Share with trading coach for code updates")
    print("="*70 + "\n")

def save_report_json(analysis, filter_stats, decision_analysis):
    """Save analysis to JSON file"""
    report = {
        'generated': datetime.now().isoformat(),
        'metrics': {
            'total_trades': analysis['total_trades'],
            'win_rate': analysis['win_rate'],
            'total_profit': analysis['total_profit'],
            'avg_win': analysis['avg_win'],
            'avg_loss': analysis['avg_loss'],
            'profit_factor': analysis['profit_factor']
        },
        'symbol_stats': analysis['symbol_stats'],
        'hour_stats': analysis['hour_stats'],
        'filter_stats': filter_stats,
        'decision_analysis': decision_analysis,
    }
    
    filename = f"weekly_report_{datetime.now().strftime('%Y_%m_%d')}.json"
    with open(filename, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"📁 Report saved: {filename}")

def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    
    print(f"\n🔍 Analyzing trades from the past {days} days...")
    
    # Load data
    trades = load_trades(days)
    filter_stats = load_filter_stats(days)
    decision_analysis = analyze_decisions(iter_decisions(days))
    filter_stats = load_filter_stats(days, iter_decisions(days))
    
    if not trades and not decision_analysis['total_decisions']:
        print("\n❌ No trades found. Run the bot first:")
        print("   python run_kite_bot.py")
        return

    if not trades:
        print("\n⚠️  Decisions were recorded, but no completed trades are available yet.")
        print(json.dumps(decision_analysis, indent=2, default=str))
        return
    
    # Analyze
    analysis = analyze_trades(trades)
    
    # Print report
    print_report(analysis, filter_stats, decision_analysis)
    
    # Save JSON
    save_report_json(analysis, filter_stats, decision_analysis)

if __name__ == '__main__':
    main()
