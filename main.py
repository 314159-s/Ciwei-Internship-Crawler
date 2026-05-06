import asyncio
import os
import csv
import re
import aiomysql  # 引入异步数据库库
from playwright.async_api import async_playwright

# --- 核心配置 ---
MAX_WORKERS = 5
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
BASE_URL = "https://www.ciwei.net"
# 搜索链接
TARGET_URL = f"{BASE_URL}/internship/search/sc1/?key=%E6%B7%B1%E5%9C%B3%E6%B0%B8%E8%91%86%E5%A5%BD%E5%A5%87%E7%A7%91%E6%8A%80%E6%9C%89%E9%99%90%E5%85%AC%E5%8F%B8"

# 数据库配置
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': '314159sql.',
    'db': 'crawl_data',
}

# 信号量控制并发
sem = asyncio.Semaphore(MAX_WORKERS)


def clean_data(text):
    """清理文本中的杂质和多余空格"""
    if not text: return "N/A"
    return re.sub(r'[\s\u00A0\u2000-\u200B\u202F\u205F\u3000]+', ' ', text).strip()


async def save_to_db(pool, title, description, url):
    """异步将数据存入 MySQL"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 这里的字段需与你在 DBeaver 中 image_c0a63d.jpg 里的表结构对应
            sql = "INSERT INTO jobs (title, description, link) VALUES (%s, %s, %s)"
            try:
                await cur.execute(sql, (title, description, url))
                await conn.commit()
                # print(f"[OK] 已存入数据库: {title[:10]}")
            except Exception as e:
                print(f"[!] 数据库写入失败: {e}")


async def fetch_detail(context, job, pool):
    """
    通过信号量控制，并行抓取详情页
    """
    async with sem:
        # 在持久化上下文中创建新页面
        page = await context.new_page()
        title = job['title']
        url = job['link']

        try:
            print(f"[*] 正在抓取: {title[:12]}...")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # 尝试定位描述内容
            try:
                desc_el = await page.wait_for_selector("ul[class^='job-desc']", timeout=5000)
                raw_text = await desc_el.inner_text()
            except:
                # 最坏情况， ul 没找到，尝试大容器
                wrap_el = await page.query_selector("div[class^='detail-wrap']")
                raw_text = await wrap_el.inner_text() if wrap_el else "未找到描述"

            description = clean_data(raw_text)

            # --- 新增：抓取完成后实时存入数据库 ---
            await save_to_db(pool, title, description, url)

            return [title, description, url]

        except Exception as e:
            print(f"[!] 抓取失败 {title}: {str(e)}")
            return [title, "Error", url]
        finally:
            await page.close()


async def main():
    # 1. 初始化数据库连接池
    pool = await aiomysql.create_pool(**DB_CONFIG)

    async with async_playwright() as p:
        # 1. 启动持久化上下文（保留登录状态）
        user_data_dir = os.path.join(os.getcwd(), "playwright_user_data")
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            args=['--start-maximized'],
            no_viewport=True,
            user_agent=USER_AGENT
        )

        # 2. 获取列表页
        page = context.pages[0] if context.pages else await context.new_page()
        print(f"[-] 访问列表页: {TARGET_URL[:50]}...")
        await page.goto(TARGET_URL)

        # 定位所有岗位链接
        # 只是定义，这句不会去查
        links_locator = page.locator('a[href*="/internship/job/"]')

        # 3. 简单的动态加载检测
        last_count = 0
        for _ in range(8):  # 最多等待约12秒
            count = await links_locator.count()
            if count > 0 and count == last_count:
                break
            last_count = count
            await asyncio.sleep(1.5)

        # 4. 提取列表数据
        jobs_to_crawl = []
        for i in range(count):
            el = links_locator.nth(i)
            href = await el.get_attribute("href")
            raw_title = await el.inner_text()

            if href and raw_title:
                full_link = f"{BASE_URL}{href}" if href.startswith('/') else href
                # 去重处理
                if not any(j['link'] == full_link for j in jobs_to_crawl):
                    jobs_to_crawl.append({
                        'title': clean_data(raw_title),
                        'link': full_link
                    })

        print(f"[+] 发现 {len(jobs_to_crawl)} 个唯一岗位，准备并行采集并入库...")

        # 5. 并发执行详情页抓取（同时传入数据库 pool）
        tasks = [fetch_detail(context, job, pool) for job in jobs_to_crawl]
        final_data = await asyncio.gather(*tasks)

        # 6. 保存 CSV 结果 (保留原有 CSV 备份习惯)
        if final_data:
            save_path = "ciwei_internship_data.csv"
            with open(save_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerow(["岗位名称", "职位描述", "详情链接"])
                writer.writerows(final_data)
            print(f"\n[DONE] 采集完成，数据已存入 CSV: {save_path}")
            print(f"[DONE] 所有合法数据已实时同步至 MySQL 数据库。")

        # 关闭浏览器
        await context.close()

    # 最后关闭连接池
    pool.close()
    await pool.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass