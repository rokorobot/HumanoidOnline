// Crawler facts shown on /crawler-policy. They mirror the crawler's code
// constants in apps/api (fetcher.USER_AGENT, robots.PRODUCT_TOKEN,
// fetcher.MIN_INTERVAL_FLOOR_SECONDS, live_adapter target cap); the API test
// tests/test_crawler_policy_page.py fails if the two drift apart.
export const CRAWLER_USER_AGENT =
  "HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)";
export const CRAWLER_PRODUCT_TOKEN = "HumanoidOnlineMarketBot";
export const CRAWLER_MIN_INTERVAL_SECONDS = 2;
export const CRAWLER_PAGES_PER_RUN = 50;
