import os
import asyncio
import discord
from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands  # 슬래시 명령어를 위한 임포트
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

# FFMPEG 경로 설정 (실제 경로로 변경 필요)
FFMPEG_PATH = "C:/ffmpeg/bin/ffmpeg.exe"  # 여러분의 ffmpeg.exe 경로로 변경하세요

# 반복 재생 모드 설정
REPEAT_MODE = {
    "NONE": 0,      # 반복 없음
    "SINGLE": 1,    # 현재 노래 반복
    "ALL": 2,       # 전체 대기열 반복
}

# 컨트롤 UI 버튼 클래스
class MusicControlButtons(View):
    def __init__(self, ctx):
        super().__init__(timeout=None)  # 버튼이 무기한 활성화되도록 설정
        self.ctx = ctx
        self.cog = ctx.cog
        
    @discord.ui.button(label="⏭️ 스킵", style=discord.ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 클릭한 사용자가 음성 채널에 있는지 확인
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!", ephemeral=True)
            
        # 봇이 재생 중인지 확인
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            return await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!", ephemeral=True)
            
        # 스킵 처리
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏭️ 노래를 건너뛰었습니다!")
        
    @discord.ui.button(label="⏹️ 중지", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 클릭한 사용자가 음성 채널에 있는지 확인
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!", ephemeral=True)
            
        # 봇이 연결되어 있는지 확인
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ 음성 채널에 연결되어 있지 않습니다!", ephemeral=True)
            
        # 중지 처리
        server_queue = self.cog.players.get(interaction.guild.id)
        if server_queue:
            server_queue.songs = []
            server_queue.repeat_mode = REPEAT_MODE["NONE"]
            
        if interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("⏹️ 재생을 중지하고 음성 채널에서 나갔습니다!")
        
    @discord.ui.button(label="🔄 반복", style=discord.ButtonStyle.success)
    async def repeat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 클릭한 사용자가 음성 채널에 있는지 확인
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!", ephemeral=True)
            
        # 봇이 재생 중인지 확인
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
            return await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!", ephemeral=True)
            
        # 반복 모드 변경
        server_queue = self.cog.players.get(interaction.guild.id)
        if not server_queue:
            return await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!", ephemeral=True)
            
        # 반복 모드 순환 (없음 -> 한 곡 -> 전체 -> 없음)
        if server_queue.repeat_mode == REPEAT_MODE["NONE"]:
            server_queue.repeat_mode = REPEAT_MODE["SINGLE"]
            await interaction.response.send_message("🔂 현재 노래를 반복합니다.")
        elif server_queue.repeat_mode == REPEAT_MODE["SINGLE"]:
            server_queue.repeat_mode = REPEAT_MODE["ALL"]
            await interaction.response.send_message("🔁 전체 대기열을 반복합니다.")
        else:
            server_queue.repeat_mode = REPEAT_MODE["NONE"]
            await interaction.response.send_message("▶️ 반복 모드를 해제했습니다.")
            
    @discord.ui.button(label="📋 대기열", style=discord.ButtonStyle.secondary)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 대기열 표시
        server_queue = self.cog.players.get(interaction.guild.id)
        if not server_queue:
            return await interaction.response.send_message("❌ 대기열이 비어있습니다!", ephemeral=True)
            
        # 대기열 임베드 생성
        await self.show_queue(interaction, server_queue)
    
    async def show_queue(self, interaction, server_queue):
        """대기열 표시 기능"""
        if not server_queue or (not server_queue.current and server_queue.queue.empty()):
            return await interaction.response.send_message("❌ 대기열이 비어있습니다!", ephemeral=True)
        
        # 큐에 있는 노래들을 리스트로 변환
        songs = []
        if server_queue.current:
            songs.append(server_queue.current)
            
        # 큐의 복사본 생성 (비동기 대기열은 직접 접근 어려움)
        temp_queue = asyncio.Queue()
        while not server_queue.queue.empty():
            song = await server_queue.queue.get()
            songs.append(song)
            await temp_queue.put(song)
            
        # 원래 큐 복원
        server_queue.queue = temp_queue
        
        # 임베드 생성
        embed = discord.Embed(
            title="🎵 재생 대기열",
            color=discord.Color.blue()
        )
        
        if len(songs) > 0:
            # 현재 재생 중인 노래
            current = songs[0]
            current_duration = f"{current.duration//60}:{current.duration%60:02d}" if current.duration else "알 수 없음"
            embed.add_field(
                name="지금 재생 중",
                value=f"[{current.title}](https://www.youtube.com/watch?v={current.data['id']}) | `{current_duration}`",
                inline=False
            )
            
            # 대기 중인 노래들
            if len(songs) > 1:
                queue_text = ""
                for i, song in enumerate(songs[1:], 1):
                    if i > 10:  # 최대 10개까지만 표시
                        queue_text += f"... 그 외 {len(songs) - 11}곡"
                        break
                    
                    duration = f"{song.duration//60}:{song.duration%60:02d}" if song.duration else "알 수 없음"
                    queue_text += f"`{i}.` [{song.title}](https://www.youtube.com/watch?v={song.data['id']}) | `{duration}`\n"
                
                embed.add_field(
                    name="대기 중인 노래",
                    value=queue_text or "대기 중인 노래가 없습니다",
                    inline=False
                )
                
            # 총 재생 시간 계산
            total_duration = sum(song.duration for song in songs if song.duration)
            hours, remainder = divmod(total_duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            if hours > 0:
                duration_str = f"{hours}시간 {minutes}분 {seconds}초"
            else:
                duration_str = f"{minutes}분 {seconds}초"
                
            embed.add_field(
                name="정보",
                value=f"▸ 총 곡 수: {len(songs)}곡\n▸ 총 재생 시간: {duration_str}",
                inline=False
            )
            
            # 반복 모드 상태
            repeat_mode = "없음"
            if server_queue.repeat_mode == REPEAT_MODE["SINGLE"]:
                repeat_mode = "한 곡 반복 🔂"
            elif server_queue.repeat_mode == REPEAT_MODE["ALL"]:
                repeat_mode = "전체 반복 🔁"
                
            embed.add_field(
                name="반복 모드",
                value=repeat_mode,
                inline=True
            )
            
        else:
            embed.description = "대기열이 비어있습니다."
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        self.repeat_mode = REPEAT_MODE["NONE"]  # 추가: 반복 모드 설정
        
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
            
            # 버튼 UI가 있는 재생 중 메시지 표시
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
                
            # 버튼 UI 생성
            view = MusicControlButtons(self.cog._get_context_from_channel(self.channel))
            
            await self.channel.send(embed=embed, view=view)
            
            # 컨트롤러 메시지 업데이트 (있는 경우)
            await self.cog.update_controller(self.guild)
            
            # 다음 노래를 재생할 때까지 대기
            await self.next.wait()
            
            # 반복 모드에 따른 처리
            if self.repeat_mode == REPEAT_MODE["SINGLE"]:
                # 현재 노래 다시 큐에 추가
                await self.queue.put(source)
            elif self.repeat_mode == REPEAT_MODE["ALL"] and self.current:
                # 현재 노래를 큐 끝에 추가
                await self.queue.put(source)
            
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
        self.controllers = {}  # 서버별 컨트롤러 메시지 저장
        
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
    
    def _get_context_from_channel(self, channel):
        """채널로부터 임시 컨텍스트 객체 생성"""
        # 버튼 인터랙션을 위한 임시 컨텍스트 생성
        fake_ctx = type('obj', (object,), {
            'bot': self.bot,
            'guild': channel.guild,
            'channel': channel,
            'cog': self,
            'voice_client': channel.guild.voice_client
        })
        return fake_ctx
    
    async def update_controller(self, guild):
        """컨트롤러 메시지 업데이트"""
        if guild.id not in self.controllers:
            return
            
        controller_message = self.controllers[guild.id]
        if not controller_message:
            return
            
        try:
            # 현재 재생 중인 노래 정보 가져오기
            server_queue = self.players.get(guild.id)
            if not server_queue:
                return
                
            # 임베드 생성
            embed = discord.Embed(
                title="🎮 음악 컨트롤러",
                description="아래 버튼을 사용하여 음악을 제어할 수 있습니다.",
                color=discord.Color.blue()
            )
            
            if server_queue.current:
                current = server_queue.current
                embed.add_field(
                    name="지금 재생 중",
                    value=f"[{current.title}](https://www.youtube.com/watch?v={current.data['id']})",
                    inline=False
                )
                
                if current.thumbnail:
                    embed.set_thumbnail(url=current.thumbnail)
                    
                if current.duration:
                    minutes, seconds = divmod(current.duration, 60)
                    embed.add_field(name="길이", value=f"{minutes}:{seconds:02d}")
                    
                # 큐 정보
                if not server_queue.queue.empty():
                    # 큐의 크기를 확인 (비동기로)
                    queue_size = server_queue.queue.qsize()
                    embed.add_field(name="대기열", value=f"{queue_size}곡", inline=True)
                    
                # 반복 모드 정보
                repeat_mode = "없음"
                if server_queue.repeat_mode == REPEAT_MODE["SINGLE"]:
                    repeat_mode = "한 곡 반복 🔂"
                elif server_queue.repeat_mode == REPEAT_MODE["ALL"]:
                    repeat_mode = "전체 반복 🔁"
                    
                embed.add_field(name="반복 모드", value=repeat_mode, inline=True)
            else:
                embed.add_field(
                    name="지금 재생 중",
                    value="재생 중인 노래가 없습니다.",
                    inline=False
                )
                
            # 버튼 UI 생성
            view = MusicControlButtons(self._get_context_from_channel(controller_message.channel))
            
            # 메시지 업데이트
            await controller_message.edit(embed=embed, view=view)
        except Exception as e:
            print(f"컨트롤러 업데이트 중 오류: {e}")
            
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
                
                # 컨트롤러 업데이트
                await self.update_controller(ctx.guild)
                
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
        
        # 컨트롤러 업데이트
        await self.update_controller(ctx.guild)
    
    @commands.command(name='대기열', aliases=['queue', 'q'])
    async def queue(self, ctx):
        """현재 재생 대기열을 표시합니다."""
        server_queue = self.players.get(ctx.guild.id)
        if not server_queue:
            return await ctx.send("❌ 대기열이 비어있습니다!")
            
        # 임시 컨텍스트 생성
        fake_ctx = self._get_context_from_channel(ctx.channel)
        
        # 대기열 표시
        buttons = MusicControlButtons(fake_ctx)
        await buttons.show_queue(ctx, server_queue)
    
    @commands.command(name='반복', aliases=['repeat', 'loop'])
    async def repeat(self, ctx, mode: str = None):
        """반복 모드를 설정합니다."""
        if not ctx.voice_client:
            return await ctx.send("❌ 재생 중인 노래가 없습니다!")
            
        if not ctx.author.voice or ctx.author.voice.channel != ctx.voice_client.channel:
            return await ctx.send("❌ 음성 채널에 먼저 입장해주세요!")
            
        server_queue = self.players.get(ctx.guild.id)
        if not server_queue:
            return await ctx.send("❌ 재생 중인 노래가 없습니다!")
            
        if mode is None:
            # 모드를 지정하지 않으면 순환
            if server_queue.repeat_mode == REPEAT_MODE["NONE"]:
                server_queue.repeat_mode = REPEAT_MODE["SINGLE"]
                await ctx.send("🔂 현재 노래를 반복합니다.")
            elif server_queue.repeat_mode == REPEAT_MODE["SINGLE"]:
                server_queue.repeat_mode = REPEAT_MODE["ALL"]
                await ctx.send("🔁 전체 대기열을 반복합니다.")
            else:
                server_queue.repeat_mode = REPEAT_MODE["NONE"]
                await ctx.send("▶️ 반복 모드를 해제했습니다.")
        elif mode.lower() in ['off', '해제', '없음']:
            server_queue.repeat_mode = REPEAT_MODE["NONE"]
            await ctx.send("▶️ 반복 모드를 해제했습니다.")
        elif mode.lower() in ['single', '한곡', '노래']:
            server_queue.repeat_mode = REPEAT_MODE["SINGLE"]
            await ctx.send("🔂 현재 노래를 반복합니다.")
        elif mode.lower() in ['all', '전체', '큐']:
            server_queue.repeat_mode = REPEAT_MODE["ALL"]
            await ctx.send("🔁 전체 대기열을 반복합니다.")
        else:
            await ctx.send("❌ 알 수 없는 모드입니다. `!반복`, `!반복 한곡`, `!반복 전체`, `!반복 해제` 중 하나를 사용하세요.")
            
        # 컨트롤러 업데이트
        await self.update_controller(ctx.guild)
        
    @commands.command(name='컨트롤러', aliases=['controller', 'c'])
    async def controller(self, ctx):
        """음악 컨트롤러를 채팅방 상단에 고정합니다."""
        # 이미 컨트롤러가 존재하는 경우 삭제
        if ctx.guild.id in self.controllers and self.controllers[ctx.guild.id]:
            try:
                await self.controllers[ctx.guild.id].delete()
            except:
                pass
                
        # 새 컨트롤러 메시지 생성
        embed = discord.Embed(
            title="🎮 음악 컨트롤러",
            description="아래 버튼을 사용하여 음악을 제어할 수 있습니다.",
            color=discord.Color.blue()
        )
        
        # 현재 재생 중인 노래 정보 추가
        server_queue = self.players.get(ctx.guild.id)
        if server_queue and server_queue.current:
            current = server_queue.current
            embed.add_field(
                name="지금 재생 중",
                value=f"[{current.title}](https://www.youtube.com/watch?v={current.data['id']})",
                inline=False
            )
            
            if current.thumbnail:
                embed.set_thumbnail(url=current.thumbnail)
        else:
            embed.add_field(
                name="지금 재생 중",
                value="재생 중인 노래가 없습니다.",
                inline=False
            )
        
        # 버튼 UI 생성
        view = MusicControlButtons(self._get_context_from_channel(ctx.channel))
        
        # 메시지 보내기
        message = await ctx.send(embed=embed, view=view)
        self.controllers[ctx.guild.id] = message
        
        # 핀 설정
        try:
            await message.pin()
        except discord.HTTPException:
            await ctx.send("⚠️ 메시지를 고정할 수 없습니다. 권한을 확인해주세요.", delete_after=10)
    
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
        embed.add_field(name="!대기열", value="현재 재생 대기열을 표시합니다", inline=False)
        embed.add_field(name="!반복 [한곡/전체/해제]", value="반복 모드를 설정합니다", inline=False)
        embed.add_field(name="!컨트롤러", value="음악 컨트롤러를 채팅방 상단에 고정합니다", inline=False)
        embed.add_field(name="!도움말", value="이 도움말을 표시합니다", inline=False)
        embed.add_field(name="/명령어", value="슬래시 명령어로도 동일한 기능을 사용할 수 있습니다", inline=False)
        
        await ctx.send(embed=embed)

    # 슬래시 명령어 (앱 명령어) 구현
    @app_commands.command(name="재생", description="노래를 검색하여 재생합니다")
    async def slash_play(self, interaction: discord.Interaction, *, 검색어: str):
        # 음성 채널 확인
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!")
            
        channel = interaction.user.voice.channel
        
        # 봇이 이미 음성 채널에 있는지 확인
        if interaction.guild.voice_client is None:
            await channel.connect()
        elif interaction.guild.voice_client.channel != channel:
            await interaction.guild.voice_client.move_to(channel)
        
        # 로딩 메시지 표시
        await interaction.response.send_message(f"🔍 `{검색어}` 검색 중...")
        
        try:
            # 임시 컨텍스트 생성
            ctx = self._get_context_from_interaction(interaction)
            
            # YouTube 검색 및 소스 생성
            source = await YTDLSource.from_url(f"ytsearch:{검색어}", loop=self.bot.loop, stream=True)
            
            # 플레이어 가져오기
            player = self.get_player(ctx)
            
            # 큐에 추가
            await player.queue.put(source)
            
            # 메시지 업데이트
            await interaction.edit_original_response(content=f"✅ **{source.title}**이(가) 대기열에 추가되었습니다!")
            
            # 컨트롤러 업데이트
            await self.update_controller(interaction.guild)
            
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ 오류 발생: {str(e)}")
            print(f"재생 중 오류: {e}")
    
    @app_commands.command(name="스킵", description="현재 재생 중인 노래를 건너뜁니다")
    async def slash_skip(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!")
            
        if not interaction.user.voice or interaction.user.voice.channel != interaction.guild.voice_client.channel:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!")
            
        if interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏭️ 노래를 건너뛰었습니다!")
        else:
            await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!")
    
    @app_commands.command(name="중지", description="재생을 중지하고 음성 채널에서 나갑니다")
    async def slash_stop(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ 음성 채널에 연결되어 있지 않습니다!")
            
        if not interaction.user.voice or interaction.user.voice.channel != interaction.guild.voice_client.channel:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!")
            
        await self.cleanup(interaction.guild)
        await interaction.response.send_message("⏹️ 재생을 중지하고 음성 채널에서 나갔습니다!")
        
        # 컨트롤러 업데이트
        await self.update_controller(interaction.guild)
    
    @app_commands.command(name="대기열", description="현재 재생 대기열을 표시합니다")
    async def slash_queue(self, interaction: discord.Interaction):
        server_queue = self.players.get(interaction.guild.id)
        if not server_queue:
            return await interaction.response.send_message("❌ 대기열이 비어있습니다!")
            
        # 임시 컨텍스트 생성
        ctx = self._get_context_from_interaction(interaction)
        
        # 대기열 표시
        buttons = MusicControlButtons(ctx)
        await interaction.response.defer()
        await buttons.show_queue(interaction, server_queue)
    
    @app_commands.command(name="반복", description="반복 모드를 설정합니다")
    @app_commands.choices(모드=[
        app_commands.Choice(name="한곡 반복", value="한곡"),
        app_commands.Choice(name="전체 반복", value="전체"),
        app_commands.Choice(name="반복 해제", value="해제")
    ])
    async def slash_repeat(self, interaction: discord.Interaction, 모드: app_commands.Choice[str] = None):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!")
            
        if not interaction.user.voice or interaction.user.voice.channel != interaction.guild.voice_client.channel:
            return await interaction.response.send_message("❌ 음성 채널에 먼저 입장해주세요!")
            
        server_queue = self.players.get(interaction.guild.id)
        if not server_queue:
            return await interaction.response.send_message("❌ 재생 중인 노래가 없습니다!")
            
        if 모드 is None:
            # 모드를 지정하지 않으면 순환
            if server_queue.repeat_mode == REPEAT_MODE["NONE"]:
                server_queue.repeat_mode = REPEAT_MODE["SINGLE"]
                await interaction.response.send_message("🔂 현재 노래를 반복합니다.")
            elif server_queue.repeat_mode == REPEAT_MODE["SINGLE"]:
                server_queue.repeat_mode = REPEAT_MODE["ALL"]
                await interaction.response.send_message("🔁 전체 대기열을 반복합니다.")
            else:
                server_queue.repeat_mode = REPEAT_MODE["NONE"]
                await interaction.response.send_message("▶️ 반복 모드를 해제했습니다.")
        else:
            # 선택한 모드로 설정
            if 모드.value == "한곡":
                server_queue.repeat_mode = REPEAT_MODE["SINGLE"]
                await interaction.response.send_message("🔂 현재 노래를 반복합니다.")
            elif 모드.value == "전체":
                server_queue.repeat_mode = REPEAT_MODE["ALL"]
                await interaction.response.send_message("🔁 전체 대기열을 반복합니다.")
            else:  # "해제"
                server_queue.repeat_mode = REPEAT_MODE["NONE"]
                await interaction.response.send_message("▶️ 반복 모드를 해제했습니다.")
                
        # 컨트롤러 업데이트
        await self.update_controller(interaction.guild)
    
    @app_commands.command(name="컨트롤러", description="음악 컨트롤러를 채팅방 상단에 고정합니다")
    async def slash_controller(self, interaction: discord.Interaction):
        # 이미 컨트롤러가 존재하는 경우 삭제
        if interaction.guild.id in self.controllers and self.controllers[interaction.guild.id]:
            try:
                await self.controllers[interaction.guild.id].delete()
            except:
                pass
                
        # 새 컨트롤러 메시지 생성
        embed = discord.Embed(
            title="🎮 음악 컨트롤러",
            description="아래 버튼을 사용하여 음악을 제어할 수 있습니다.",
            color=discord.Color.blue()
        )
        
        # 현재 재생 중인 노래 정보 추가
        server_queue = self.players.get(interaction.guild.id)
        if server_queue and server_queue.current:
            current = server_queue.current
            embed.add_field(
                name="지금 재생 중",
                value=f"[{current.title}](https://www.youtube.com/watch?v={current.data['id']})",
                inline=False
            )
            
            if current.thumbnail:
                embed.set_thumbnail(url=current.thumbnail)
        else:
            embed.add_field(
                name="지금 재생 중",
                value="재생 중인 노래가 없습니다.",
                inline=False
            )
        
        # 임시 컨텍스트 생성
        ctx = self._get_context_from_interaction(interaction)
        
        # 버튼 UI 생성
        view = MusicControlButtons(ctx)
        
        # 응답 전송
        await interaction.response.send_message("🎮 컨트롤러 생성 중...")
        
        # 메시지 보내기
        message = await interaction.channel.send(embed=embed, view=view)
        self.controllers[interaction.guild.id] = message
        
        # 원래 메시지 수정
        await interaction.edit_original_response(content="✅ 컨트롤러가 생성되었습니다!")
        
        # 핀 설정
        try:
            await message.pin()
        except discord.HTTPException:
            await interaction.followup.send("⚠️ 메시지를 고정할 수 없습니다. 권한을 확인해주세요.", ephemeral=True)
    
    def _get_context_from_interaction(self, interaction):
        """Interaction에서 임시 컨텍스트 객체 생성"""
        fake_ctx = type('obj', (object,), {
            'bot': self.bot,
            'guild': interaction.guild,
            'channel': interaction.channel,
            'cog': self,
            'voice_client': interaction.guild.voice_client
        })
        return fake_ctx

# Cog 등록 및 봇 실행
async def setup():
    music_cog = Music(bot)
    await bot.add_cog(music_cog)
    
    # 슬래시 명령어 동기화
    try:
        # 슬래시 명령어 등록
        await bot.tree.sync()
        print("슬래시 명령어가 성공적으로 동기화되었습니다.")
    except Exception as e:
        print(f"슬래시 명령어 동기화 중 오류 발생: {e}")
    
@bot.event
async def on_ready():
    print(f'{bot.user.name}이(가) 온라인 상태입니다!')
    await setup()
    # 봇 상태 설정
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="/재생 또는 !재생 | 음악 봇"
        )
    )

# 추가: 에러 핸들링
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        # 명령어를 찾을 수 없는 경우, 유사한 명령어인지 확인
        search_term = ctx.message.content.lstrip('!').split()[0]
        
        # 명령어로 인식되지 않은 채팅이 노래 제목인지 확인 (접두사 없는 명령어)
        if not search_term.startswith('!') and len(search_term) > 1:
            # Music 코그 가져오기
            music_cog = bot.get_cog('Music')
            if music_cog:
                # 유사 노래 검색 시작
                await music_cog.play(ctx, search=ctx.message.content)
                return
            
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

# 일반 채팅 메시지 처리 (접두사 없이 노래 제목만 입력 시 재생)
@bot.event
async def on_message(message):
    # 봇 메시지 무시
    if message.author.bot:
        return
    
    # 슬래시 명령어나 일반 명령어 무시
    if message.content.startswith('!') or message.content.startswith('/'):
        await bot.process_commands(message)
        return
    
    # 짧은 메시지 (1-2단어) 무시
    words = message.content.split()
    if len(words) < 2 and len(message.content) < 10:
        await bot.process_commands(message)
        return
    
    # 음성 채널에 있는지 확인
    if message.author.voice and message.author.voice.channel:
        # 재생 명령어와 같은 기능으로 처리
        ctx = await bot.get_context(message)
        music_cog = bot.get_cog('Music')
        if music_cog:
            await music_cog.play(ctx, search=message.content)
    else:
        # 일반 메시지로 처리
        await bot.process_commands(message)

# 봇 실행
bot.run(TOKEN)