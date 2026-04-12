import asyncio
import os
import csv
from playwright.async_api import async_playwright


async def scrape_ciwei_robust():
    async with async_playwright() as p:
        # 1. 环境准备
        user_data_dir = os.path.join(os.getcwd(), "playwright_user_data")

        # 强制设置成大屏幕桌面模式，防止被网站识别为移动端导致跳转
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            args=['--start-maximized'],
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # 2. 访问目标 URL
        url = "https://www.ciwei.net/internship/search/sc1/?key=%E6%B7%B1%E5%9C%B3%E6%B0%B8%E8%91%86%E5%A5%BD%E5%A5%87%E7%A7%91%E6%8A%80%E6%9C%89%E9%99%90%E5%85%AC%E5%8F%B8"
        print(f"正在打开页面: {url}")
        await page.goto(url)

        # 3. 智能等待：不找特定 Class，找包含 "/job/" 的链接
        print("\n[状态] 正在寻找岗位链接...")
        job_links_locator = page.locator('a[href*="/internship/job/"]')

        # 循环检测，直到页面上出现了这类链接
        while True:
            count = await job_links_locator.count()
            if count > 0:
                print(f" 成功！检测到 {count} 个岗位链接。")
                break
            else:
                # 如果没找到，打印一下当前页面的文本，帮我们判断状态
                print("暂未发现岗位。请确保浏览器已登录并显示了列表（手动刷新一下页面也行）...")
                await asyncio.sleep(4)

        # 4. 提取岗位名称和链接
        jobs_list = []
        for i in range(count):
            link_el = job_links_locator.nth(i)
            href = await link_el.get_attribute("href")
            # 向上寻找最近的文本作为标题，或者直接取链接内的文本
            title = await link_el.inner_text()
            # 简单清洗标题（去除换行和多余空格）
            title = " ".join(title.split())

            if href and title:
                full_link = f"https://www.ciwei.net{href}" if href.startswith("/") else href
                # 防止重复添加
                if not any(j['link'] == full_link for j in jobs_list):
                    jobs_list.append({"title": title, "link": full_link})

        print(f"准备开始爬取 {len(jobs_list)} 个岗位的详细描述...")

        # 5. 抓取详情页
        final_results = []
        for job in jobs_list:
            print(f" -> 正在抓取: {job['title'][:20]}...")
            #新建网页用来打开详见页
            detail_page = await context.new_page()
            try:
                #打开详情页
                await detail_page.goto(job['link'], wait_until="networkidle", timeout=20000)

                # 详情页描述提取优化：寻找包含“工作职责”或“岗位要求”的父级容器
                # 这里我们用一个比较宽泛的定位：包含“描述”或“职责”的 div
                await detail_page.wait_for_timeout(2000)  # 给 SPA 一点渲染时间

                # 尝试多个可能的描述区域
                selectors = [".job-detail-box", ".job-description", "div[class*='jobDetail']", "div[class*='content']"]
                description = "未找到描述"

                for selector in selectors:
                    desc_el = await detail_page.query_selector(selector)
                    if desc_el:
                        description = (await desc_el.inner_text()).strip()
                        break
                #存下职位名称，内容，链接
                final_results.append([job['title'], description, job['link']])
            except Exception as e:
                print(f"     详情页加载超时: {job['link']}")
            finally:
                await detail_page.close()

        # 6. 保存数据
        if final_results:
            filename = "ciwei_data.csv"
            with open(filename, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["岗位名称", "职位描述", "详情链接"])
                writer.writerows(final_results)
            print(f"\n 任务完成！已保存到: {os.path.abspath(filename)}")
        else:
            print("\n未抓取到任何有效数据。")

        await context.close()


if __name__ == "__main__":
    asyncio.run(scrape_ciwei_robust())