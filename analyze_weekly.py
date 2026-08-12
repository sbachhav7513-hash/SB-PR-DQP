#!/usr/bin/env python3
"""
Weekly Analysis Tool - Run every Friday to generate metrics
Usage: python analyze_weekly.py [days=7]
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

def load_trades(days=7):
    """Load trades from the past N days"""
    trades = []
    trades_file = Path('trades.jsonl')
    
    if not trades_file.exists():
        print("❌ ERROR: trades.jsonl not found!")
        print("   Make sure the bot has run and created trades.jsonl")
        return []
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    try:
        with open(trades_file, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        trade = json.loads(line)
                        trade_time = datetime.fromisoformat(trade.get('timestamp', ''))
                        
                        if trade_time > cutoff_date:
                            trades.append(trade)
                    except (json.JSONDecodeError, ValueError) as e:
                        continue
    except Exception as e:
        print(f"❌ Error reading trades.jsonl: {e}")
        return []
    
    return trades

def load_filter_stats(days=7):
    """Load filter statistics"""
    stats = {
        'volatility_rejected': 0,
        'confirmation_rejected': 0,
        'cooldown_rejected': 0,
        'hours_rejected': 0,
        'threshold_rejected': 0,
        'approved_entries': 0
    }
    
    filter_log = Path('filter_log.jsonl')
    
    if not filter_log.exists():
        print("⚠️  Note: filter_log.jsonl not found yet (will be created after bot runs with updated code)")
        return stats
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    try:
        with open(filter_log, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        entry_time = datetime.fromisoformat(entry.get('timestamp', ''))
                        
                        if entry_time > cutoff_date:
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
    wins = [t for t in trades if t.get('profit', 0) > 0]
    losses = [t for t in trades if t.get('profit', 0) <= 0]
    win_count = len(wins)
    loss_count = len(losses)
    
    # Financial metrics
    total_profit = sum(t.get('profit', 0) for t in trades)
    win_sum = sum(t.get('profit', 0) for t in wins) if wins else 0
    loss_sum = sum(t.get('profit', 0) for t in losses) if losses else 0
    
    avg_win = win_sum / len(wins) if wins else 0
    avg_loss = loss_sum / len(losses) if losses else 0
    profit_factor = win_sum / abs(loss_sum) if loss_sum != 0 else 0
    
    # By symbol
    symbol_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'profit': 0, 'count': 0})
    
    for trade in trades:
        symbol = trade.get('symbol', 'UNKNOWN')
        profit = trade.get('profit', 0)
        symbol_stats[symbol]['count'] += 1
        symbol_stats[symbol]['profit'] += profit
        
        if profit > 0:
            symbol_stats[symbol]['wins'] += 1
        else:
            symbol_stats[symbol]['losses'] += 1
    
    # By hour
    hour_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'profit': 0, 'count': 0})
    
    for trade in trades:
        try:
            trade_time = datetime.fromisoformat(trade.get('timestamp', ''))
            hour = trade_time.hour
            profit = trade.get('profit', 0)
            
            hour_stats[hour]['count'] += 1
            hour_stats[hour]['profit'] += profit
            
            if profit > 0:
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
        'largest_win': max((t.get('profit', 0) for t in trades), default=0),
        'largest_loss': min((t.get('profit', 0) for t in trades), default=0),
        'symbol_stats': dict(symbol_stats),
        'hour_stats': dict(hour_stats),
        'trades': trades
    }

def print_report(analysis, filter_stats):
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

def save_report_json(analysis, filter_stats):
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
        'filter_stats': filter_stats
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
    
    if not trades:
        print("\n❌ No trades found. Run the bot first:")
        print("   python run_kite_bot.py")
        return
    
    # Analyze
    analysis = analyze_trades(trades)
    
    # Print report
    print_report(analysis, filter_stats)
    
    # Save JSON
    save_report_json(analysis, filter_stats)

if __name__ == '__main__':
    main()
