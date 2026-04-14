import asyncio
import os
import csv
import re  # 导入正则库，用于强力清洗乱码
from playwright.async_api import async_playwright


async def scrape_ciwei_robust():
    async with async_playwright() as p:
        # 1. 环境准备
        user_data_dir = os.path.join(os.getcwd(), "playwright_user_data")

        # 强制设置成大屏幕桌面模式，防止被网站识别为移动端导致跳转
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            # 不隐藏浏览器页面
            headless=False,
            args=['--start-maximized'],
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

        # 得到第一个空白标签页
        page = context.pages[0] if context.pages else await context.new_page()

        # 2. 访问目标 URL
        url = "https://www.ciwei.net/internship/search/sc1/?key=%E6%B7%B1%E5%9C%B3%E6%B0%B8%E8%91%86%E5%A5%BD%E5%A5%87%E7%A7%91%E6%8A%80%E6%9C%89%E9%99%90%E5%85%AC%E5%8F%B8"
        print(f"正在打开页面: {url}")
        await page.goto(url)

        # 3. 智能等待：不找特定 Class，找包含 "/job/" 的链接
        print("\n[状态] 正在寻找岗位链接...")
        # 根据属性来定位所有岗位链接
        job_links_locator = page.locator('a[href*="/internship/job/"]')

        # 循环检测，直到页面上出现了这类链接
        last_count = 0
        while True:
            # 由于程序和浏览器是不同线程，所以需要关键词保证能真正得到通过计算得到的岗位数，哪怕可能此时浏览器计算得到的岗位数未必是对的
            # 而不会因为没用直接反馈而直接视为0
            count = await job_links_locator.count()
            if count > 0 and count == last_count:
                # 只有当岗位数连续两次检查都一样，且不为0时，才认为加载完了
                print(f"数据已稳定，共检测到 {count} 个岗位。")
                break
            last_count = count
            print(f"正在等待数据加载...当前检测到 {count} 个...")
            await asyncio.sleep(2)  # 缩短等待时间，多查几次

        # 4. 提取岗位名称和链接
        jobs_list = []
        # 借助开始用定位器得到的标签组德奥每个岗位的每次和链接
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
            # 新建网页用来打开详见页
            detail_page = await context.new_page()
            try:
                # 打开详情页
                await detail_page.goto(job['link'], wait_until="domcontentloaded", timeout=20000)

                # 【关键点】等待 span 标签出现，这代表具体的描述文字已经渲染出来了
                try:
                    await detail_page.wait_for_selector("ul[class^='job-desc'] span", timeout=8000)
                except:
                    # 如果超时，说明可能是另一种模板，多等 2 秒作为兜底
                    await detail_page.wait_for_timeout(2000)

                # 详情页描述提取优化：寻找包含“工作职责”或“岗位要求”的父级容器
                # 1. 尝试寻找最精准的描述列表
                selectors = [
                    "ul[class^='job-desc']",  # 你的 F12 截图里最核心的列表
                    "div[class^='detail-wrap']"  # 包裹列表的大盒子
                ]

                description = "未找到描述"

                for selector in selectors:
                    # 根据上面的可能的类名搜出所有可能标签
                    desc_el = await detail_page.query_selector(selector)
                    if desc_el:
                        # 使用 inner_text 获取格式化好的文本
                        raw_text = await desc_el.inner_text()

                        # --- 【排版核心改进点：彻底清除 NBSP 并强制换行】 ---
                        # A. 强力清除所有不可见的空格字符（包括 \xa0, \u2002 等）
                        clean_text = re.sub(r'[\s\u00A0\u2000-\u200B\u202F\u205F\u3000]+', ' ', raw_text)

                        # B. 处理换行：先按行分割，再重新用标准的系统换行符拼接
                        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
                        description = "\n".join(lines)

                        if len(description) > 30:
                            break

                # 存下职位名称，内容，链接
                final_results.append([job['title'], description, job['link']])
            except Exception as e:
                print(f"     详情页加载超时/异常: {job['link']} | 错误: {e}")
            finally:
                await detail_page.close()

        # 6. 保存数据
        if final_results:
            filename = "ciwei_data.csv"
            # 使用 utf-8-sig 确保 Excel 打开时不乱码
            # quoting=csv.QUOTE_ALL 强制给所有内容加双引号，确保换行符在 CSV 单元格内生效
            with open(filename, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerow(["岗位名称", "职位描述", "详情链接"])
                writer.writerows(final_results)
            print(f"\n 任务完成！已保存到: {os.path.abspath(filename)}")
            print("【提示】在 VS Code 中查看请按 Ctrl+Shift+V 预览，或使用 Excel 打开并开启『自动换行』。")
        else:
            print("\n未抓取到任何有效数据。")

        await context.close()


if __name__ == "__main__":
    asyncio.run(scrape_ciwei_robust())