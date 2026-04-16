import asyncio
import os
import csv
import re
from playwright.async_api import async_playwright

# 设置最大并发数，防止内存溢出或被封 IP
MAX_CONCURRENT_TASKS = 5
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

#定义专门负责抓取单个详情页的异步任务
async def fetch_job_detail(context, job):

    # 使用信号量控制并发，确保同时只有 MAX_CONCURRENT_TASKS 个任务在运行
    async with semaphore:
        print(f" -> 正在并行抓取: {job['title'][:15]}...")
        #开网站
        detail_page = await context.new_page()
        description = "未找到描述"

        try:
            # 1. 访问页面
            await detail_page.goto(job['link'], wait_until="domcontentloaded", timeout=20000)

            # 2. 等待内容渲染，确保包含需要信息的部分渲染出来了
            try:
                await detail_page.wait_for_selector("ul[class^='job-desc'] span", timeout=8000)
            except:
                await detail_page.wait_for_timeout(2000)

            # 3. 提取数据
            ul_el = await detail_page.query_selector("ul[class^='job-desc']")
            if ul_el:
                li_elements = await ul_el.query_selector_all("li")
                lines = [re.sub(r'[\s\u00A0\u2000-\u200B\u202F\u205F\u3000]+', ' ', await li.inner_text()).strip()
                         for li in li_elements]
                #以防万一去掉空行
                lines = [l for l in lines if l]
                if lines:
                    description = "\n".join(lines)

            # 4. 保底逻辑
            if description == "未找到描述" or len(description) < 10:
                wrap_el = await detail_page.query_selector("div[class^='detail-wrap']")
                if wrap_el:
                    raw_text = await wrap_el.inner_text()
                    clean_text = re.sub(r'[\s\u00A0\u2000-\u200B\u202F\u205F\u3000]+', ' ', raw_text)
                    description = "\n".join([l.strip() for l in clean_text.splitlines() if l.strip()])

            return [job['title'], description, job['link']]

        except Exception as e:
            print(f"     [错误] 抓取失败 {job['title'][:10]}: {e}")
            return [job['title'], "抓取异常", job['link']]
        finally:
            # 必须关闭页面，否则内存会爆
            await detail_page.close()


async def scrape_ciwei_robust():
    async with async_playwright() as p:
        user_data_dir = os.path.join(os.getcwd(), "playwright_user_data")
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            args=['--start-maximized'],
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # 2 & 3: 获取列表页（这部分保持串行，因为只有一个列表页）
        url = "https://www.ciwei.net/internship/search/sc1/?key=%E6%B7%B1%E5%9C%B3%E6%B0%B8%E8%91%86%E5%A5%BD%E5%A5%87%E7%A7%91%E6%8A%80%E6%9C%89%E9%99%90%E5%85%AC%E5%8F%B8"
        await page.goto(url)
        job_links_locator = page.locator('a[href*="/internship/job/"]')

        last_count = 0
        while True:
            count = await job_links_locator.count()
            if count > 0 and count == last_count: break
            last_count = count
            await asyncio.sleep(2)

        jobs_list = []
        for i in range(count):
            link_el = job_links_locator.nth(i)
            href = await link_el.get_attribute("href")
            title = " ".join((await link_el.inner_text()).split())
            if href and title:
                full_link = f"https://www.ciwei.net{href}"
                if not any(j['link'] == full_link for j in jobs_list):
                    jobs_list.append({"title": title, "link": full_link})

        print(f"\n[威力开启] 准备并行爬取 {len(jobs_list)} 个岗位...")

        # 5: 并行抓取详情页
        # 1. 批量创建任务对象
        tasks = [fetch_job_detail(context, job) for job in jobs_list]

        # 2. 统一收割结果
        # gather 会并发运行所有任务，并按照 jobs_list 的顺序返回结果
        final_results = await asyncio.gather(*tasks)

        # 6: 保存数据
        if final_results:
            filename = "ciwei_data_parallel.csv"
            with open(filename, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerow(["岗位名称", "职位描述", "详情链接"])
                writer.writerows(final_results)
            print(f"\n并发任务完成！总数: {len(final_results)}，保存至: {filename}")

        await context.close()


if __name__ == "__main__":
    asyncio.run(scrape_ciwei_robust())