import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp
import ffmpeg

# yt-dlp 옵션 설정
yt_dlp.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # IPv6 주소에서 바인딩 문제 방지
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# .env 파일에서 환경 변수 로드
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# FFMPEG 경로 설정 (여기를 수정하세요)
FFMPEG_PATH = "C:/ffmpeg/bin/ffmpeg.exe"  # 실제 ffmpeg.exe 경로로 변경하세요!

# 유튜브 검색 및 재생을 위한 클래스
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            # 플레이리스트에서 첫 번째 항목 가져오기
            data = data['entries'][0]
            
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        # ffmpeg 경로 직접 지정
        return cls(discord.FFmpegPCMAudio(
            filename, 
            executable=FFMPEG_PATH,  # 직접 ffmpeg 경로 지정
            **ffmpeg_options
        ), data=data)

# 음악 큐 관리를 위한 클래스
class MusicPlayer:
    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.cog = ctx.cog
        
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        
        self.current = None
        self.volume = 0.5
        
        ctx.bot.loop.create_task(self.player_loop())
        
    async def player_loop(self):
        """음악 재생 루프"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            self.next.clear()
            
            # 큐에서 다음 항목 가져오기
            try:
                async with asyncio.timeout(300):  # 5분 동안 대기
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                # 시간 초과시 음성 연결 종료
                await self.destroy(self.guild)
                return
                
            # 음성 클라이언트가 연결되었는지 확인
            if not self.guild.voice_client:
                return
                
            # 현재 재생 중인 곡 설정
            self.current = source
            
            # 노래 재생
            self.guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            
            # 재생 중인 노래 정보 표시
            embed = discord.Embed(
                title="🎵 지금 재생 중",
                description=f"[{source.title}](https://www.youtube.com/watch?v={source.data['id']})",
                color=discord.Color.blue()
            )
            
            if source.thumbnail:
                embed.set_thumbnail(url=source.thumbnail)
                
            if source.duration:
                minutes, seconds = divmod(source.duration, 60)
                embed.add_field(name="길이", value=f"{minutes}:{seconds:02d}")
                
            await self.channel.send(embed=embed)
            
            # 다음 노래를 재생할 때까지 대기
            await self.next.wait()
            
            # 다음 노래를 위해 현재 소스 정리
            source.cleanup()
            self.current = None
            
    async def destroy(self, guild):
        """플레이어 정리 및 종료"""
        return self.bot.loop.create_task(self.cog.cleanup(guild))

# 음악 명령어 관리를 위한 Cog
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        
    async def cleanup(self, guild):
        """플레이어 정리 및 음성 연결 종료"""
        try:
            await guild.voice_client.disconnect()
        except AttributeError:
            pass
            
        try:
            del self.players[guild.id]
        except KeyError:
            pass
            
    def get_player(self, ctx):
        """서버에 플레이어 가져오기 또는 생성"""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player
            
        return player
        
    @commands.command(name='재생', aliases=['play', 'p'])
    async def play(self, ctx, *, search: str):
        """노래를 검색하여 재생합니다."""
        # 음성 채널 확인
        if not ctx.author.voice:
            return await ctx.send("❌ 음성 채널에 먼저 입장해주세요!")
            
        channel = ctx.author.voice.channel
        
        # 봇이 이미 음성 채널에 있는지 확인
        if ctx.voice_client is None:
            await channel.connect()
        elif ctx.voice_client.channel != channel:
            await ctx.voice_client.move_to(channel)
            
        # 검색 메시지 표시
        loading_msg = await ctx.send(f"🔍 `{search}` 검색 중...")
        
        async with ctx.typing():
            try:
                # YouTube 검색 및 소스 생성
                source = await YTDLSource.from_url(f"ytsearch:{search}", loop=self.bot.loop, stream=True)
                
                # 플레이어 가져오기
                player = self.get_player(ctx)
                
                # 큐에 추가
                await player.queue.put(source)
                
                # 로딩 메시지 업데이트
                await loading_msg.edit(content=f"✅ **{source.title}**이(가) 대기열에 추가되었습니다!")
                
            except Exception as e:
                await ctx.send(f"❌ 오류 발생: {str(e)}")
                print(f"재생 중 오류: {e}")
                
    @commands.command(name='스킵', aliases=['skip', 's'])
    async def skip(self, ctx):
        """현재 재생 중인 노래를 건너뜁니다."""
        if not ctx.voice_client:
            return await ctx.send("❌ 재생 중인 노래가 없습니다!")
            
        if not ctx.author.voice or ctx.author.voice.channel != ctx.voice_client.channel:
            return await ctx.send("❌ 음성 채널에 먼저 입장해주세요!")
            
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ 노래를 건너뛰었습니다!")
            
    @commands.command(name='중지', aliases=['stop'])
    async def stop(self, ctx):
        """재생을 중지하고 음성 채널에서 나갑니다."""
        if not ctx.voice_client:
            return await ctx.send("❌ 음성 채널에 연결되어 있지 않습니다!")
            
        if not ctx.author.voice or ctx.author.voice.channel != ctx.voice_client.channel:
            return await ctx.send("❌ 음성 채널에 먼저 입장해주세요!")
            
        await self.cleanup(ctx.guild)
        await ctx.send("⏹️ 재생을 중지하고 음성 채널에서 나갔습니다!")
        
    @commands.command(name='도움말', aliases=['h', 'help'])
    async def help(self, ctx):
        """명령어 도움말을 표시합니다."""
        embed = discord.Embed(
            title="🎵 음악 봇 도움말",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="!재생 [노래 제목]", value="노래를 검색하여 재생합니다", inline=False)
        embed.add_field(name="!스킵", value="현재 재생 중인 노래를 건너뜁니다", inline=False)
        embed.add_field(name="!중지", value="재생을 중지하고 음성 채널에서 나갑니다", inline=False)
        embed.add_field(name="!도움말", value="이 도움말을 표시합니다", inline=False)
        
        await ctx.send(embed=embed)

# Cog 등록 및 봇 실행
async def setup():
    await bot.add_cog(Music(bot))
    
@bot.event
async def on_ready():
    print(f'{bot.user.name}이(가) 온라인 상태입니다!')
    await setup()

# 추가: 에러 핸들링
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ 알 수 없는 명령어입니다. `!도움말`을 입력하여 명령어 목록을 확인하세요.")
    elif isinstance(error, commands.MissingRequiredArgument):
        if ctx.command.name == "재생" or ctx.command.name == "play" or ctx.command.name == "p":
            await ctx.send("❌ 노래 제목을 입력해주세요. 예시: `!재생 아이유 좋은날`")
        else:
            await ctx.send(f"❌ 명령어 사용법이 잘못되었습니다. `!도움말`을 입력하여 명령어 사용법을 확인하세요.")
    else:
        print(f"오류 발생: {type(error).__name__}: {error}")
        await ctx.send(f"❌ 명령어 실행 중 오류가 발생했습니다: {type(error).__name__}")

# 디버깅 에러 핸들링
@bot.event
async def on_error(event, *args, **kwargs):
    print(f"이벤트 {event}에서 오류 발생:")
    import traceback
    traceback.print_exc()

# 봇 실행
bot.run(TOKEN)