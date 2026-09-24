/**
 * DigitalCLIQ AI team: nightly Google Ads export to Google Sheets. READ-ONLY.
 * This script never changes anything in the account. It only reads and writes a Sheet.
 *
 * Install (per Ads account): Tools > Bulk actions > Scripts > + New script, paste,
 * Authorize, Preview once, then set Frequency: Daily, 12 AM.
 * First run with SPREADSHEET_URL blank creates the Sheet and logs its URL.
 * Paste that URL below so later runs reuse the same Sheet, then give the
 * Sheet id to Shaq (references/data-sources.md).
 */
var SPREADSHEET_URL = '';
var STORE_CODE = 'MCP'; // MCP, NOI, or ATLAS

var REPORTS = [
  {
    tab: 'campaign_daily_30d',
    query:
      "SELECT segments.date, campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, " +
      "campaign_budget.amount_micros, metrics.impressions, metrics.clicks, metrics.cost_micros, " +
      "metrics.conversions, metrics.conversions_value, metrics.search_impression_share, " +
      "metrics.search_budget_lost_impression_share, metrics.search_rank_lost_impression_share " +
      "FROM campaign WHERE segments.date DURING LAST_30_DAYS AND campaign.status != 'REMOVED' " +
      "ORDER BY segments.date DESC",
    cols: ['segments.date', 'campaign.id', 'campaign.name', 'campaign.status', 'campaign.advertisingChannelType',
      'campaignBudget.amountMicros', 'metrics.impressions', 'metrics.clicks', 'metrics.costMicros',
      'metrics.conversions', 'metrics.conversionsValue', 'metrics.searchImpressionShare',
      'metrics.searchBudgetLostImpressionShare', 'metrics.searchRankLostImpressionShare']
  },
  {
    tab: 'adgroup_7d',
    query:
      "SELECT campaign.name, ad_group.name, ad_group.status, metrics.impressions, metrics.clicks, " +
      "metrics.cost_micros, metrics.conversions FROM ad_group " +
      "WHERE segments.date DURING LAST_7_DAYS AND metrics.impressions > 0 ORDER BY metrics.cost_micros DESC LIMIT 300",
    cols: ['campaign.name', 'adGroup.name', 'adGroup.status', 'metrics.impressions', 'metrics.clicks',
      'metrics.costMicros', 'metrics.conversions']
  },
  {
    tab: 'search_terms_7d',
    query:
      "SELECT search_term_view.search_term, search_term_view.status, campaign.name, ad_group.name, " +
      "metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions FROM search_term_view " +
      "WHERE segments.date DURING LAST_7_DAYS ORDER BY metrics.cost_micros DESC LIMIT 300",
    cols: ['searchTermView.searchTerm', 'searchTermView.status', 'campaign.name', 'adGroup.name',
      'metrics.impressions', 'metrics.clicks', 'metrics.costMicros', 'metrics.conversions']
  },
  {
    tab: 'keywords_7d',
    query:
      "SELECT campaign.name, ad_group.name, ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, " +
      "ad_group_criterion.quality_info.quality_score, metrics.impressions, metrics.clicks, metrics.cost_micros, " +
      "metrics.conversions FROM keyword_view WHERE segments.date DURING LAST_7_DAYS " +
      "ORDER BY metrics.cost_micros DESC LIMIT 300",
    cols: ['campaign.name', 'adGroup.name', 'adGroupCriterion.keyword.text', 'adGroupCriterion.keyword.matchType',
      'adGroupCriterion.qualityInfo.qualityScore', 'metrics.impressions', 'metrics.clicks', 'metrics.costMicros',
      'metrics.conversions']
  },
  {
    tab: 'conversions_by_action_7d',
    query:
      "SELECT campaign.name, segments.conversion_action_name, metrics.conversions, metrics.all_conversions " +
      "FROM campaign WHERE segments.date DURING LAST_7_DAYS AND metrics.all_conversions > 0",
    cols: ['campaign.name', 'segments.conversionActionName', 'metrics.conversions', 'metrics.allConversions']
  },
  {
    tab: 'change_events_14d',
    query:
      "SELECT change_event.change_date_time, change_event.user_email, change_event.client_type, " +
      "change_event.change_resource_type, change_event.resource_change_operation, change_event.changed_fields, " +
      "campaign.name FROM change_event WHERE change_event.change_date_time DURING LAST_14_DAYS " +
      "ORDER BY change_event.change_date_time DESC LIMIT 200",
    cols: ['changeEvent.changeDateTime', 'changeEvent.userEmail', 'changeEvent.clientType',
      'changeEvent.changeResourceType', 'changeEvent.resourceChangeOperation', 'changeEvent.changedFields',
      'campaign.name']
  },
  {
    tab: 'ads_policy_issues',
    query:
      "SELECT campaign.name, ad_group.name, ad_group_ad.ad.id, ad_group_ad.ad.type, " +
      "ad_group_ad.policy_summary.approval_status, ad_group_ad.policy_summary.review_status FROM ad_group_ad " +
      "WHERE ad_group_ad.status = 'ENABLED' AND campaign.status = 'ENABLED' " +
      "AND ad_group_ad.policy_summary.approval_status IN ('DISAPPROVED', 'APPROVED_LIMITED', 'AREA_OF_INTEREST_ONLY')",
    cols: ['campaign.name', 'adGroup.name', 'adGroupAd.ad.id', 'adGroupAd.ad.type',
      'adGroupAd.policySummary.approvalStatus', 'adGroupAd.policySummary.reviewStatus']
  }
];

function main() {
  var ss = SPREADSHEET_URL
    ? SpreadsheetApp.openByUrl(SPREADSHEET_URL)
    : SpreadsheetApp.create('AI Team Ads Export - ' + STORE_CODE);
  if (!SPREADSHEET_URL) Logger.log('NEW SHEET, paste into SPREADSHEET_URL: ' + ss.getUrl());

  var status = [];
  REPORTS.forEach(function (r) {
    try {
      var rows = [r.cols.map(header)];
      var it = AdsApp.search(r.query);
      while (it.hasNext()) {
        var row = it.next();
        rows.push(r.cols.map(function (c) { return cell(c, dig(row, c)); }));
      }
      writeTab(ss, r.tab, rows);
      status.push([r.tab, rows.length - 1, 'ok']);
    } catch (e) {
      status.push([r.tab, 0, 'ERROR: ' + e]);
    }
  });

  var acct = AdsApp.currentAccount();
  var meta = [
    ['store', STORE_CODE],
    ['account_name', acct.getName()],
    ['currency', acct.getCurrencyCode()],
    ['account_timezone', acct.getTimeZone()],
    ['last_run', Utilities.formatDate(new Date(), acct.getTimeZone(), "yyyy-MM-dd HH:mm:ss")],
    ['note', 'cost columns are already converted from micros to currency units'],
    ['', ''],
    ['tab', 'rows', 'status']
  ].map(function (r) { return [r[0], r[1], r[2] || '']; }).concat(status);
  writeTab(ss, 'meta', meta);
}

function dig(obj, path) {
  return path.split('.').reduce(function (o, k) { return o == null ? null : o[k]; }, obj);
}

function header(path) {
  return path.replace(/Micros$/, '').replace(/\./g, '_');
}

function cell(path, v) {
  if (v == null) return '';
  if (/Micros$/.test(path)) return Number(v) / 1000000;
  if (Array.isArray(v)) return v.join(', ');
  if (typeof v === 'object') return JSON.stringify(v);
  return v;
}

function writeTab(ss, name, rows) {
  var sh = ss.getSheetByName(name) || ss.insertSheet(name);
  sh.clearContents();
  if (rows.length) sh.getRange(1, 1, rows.length, rows[0].length).setValues(rows);
}
